import { HTTPError, type NormalizedOptions } from 'ky';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '@/lib/api/talk';
import {
    selectIsAtMessageLimit,
    selectIsSendDisabled,
    useChatStore,
} from '@/stores/chat-store';
import type {
    ChatSessionDetail,
    ChatSessionListItem,
    ChatSessionMessage,
    ChatUiMessage,
    GenerateConfig,
} from '@/types/talk';
import {
    controlledStream,
    type ControlledStream,
} from '../helpers/chat-stream';

vi.mock('@/lib/api/talk', () => ({
    bulkDeleteAudio: vi.fn(),
    createSession: vi.fn(),
    deleteAudio: vi.fn(),
    deleteSession: vi.fn(),
    fetchAudioBlob: vi.fn(),
    fetchConfigs: vi.fn(),
    getSession: vi.fn(),
    listSessions: vi.fn(),
    streamEdit: vi.fn(),
    streamMessage: vi.fn(),
    updateSessionTitle: vi.fn(),
}));

const NOW = '2026-11-02T09:30:00+09:00';
const LATER = '2026-11-02T09:31:00+09:00';

function serverMessage(
    overrides: Partial<ChatSessionMessage> = {},
): ChatSessionMessage {
    return {
        id: 1,
        sequence: 0,
        role: 'user',
        content: 'おはよう',
        audio_url: null,
        audio_format: '',
        audio_size_bytes: 0,
        created_at: NOW,
        ...overrides,
    };
}

function assistantMessage(
    overrides: Partial<ChatSessionMessage> = {},
): ChatSessionMessage {
    return serverMessage({
        id: 2,
        sequence: 1,
        role: 'assistant',
        content: 'おはようございます',
        ...overrides,
    });
}

function detail(
    messages: readonly ChatSessionMessage[] = [],
    overrides: Partial<ChatSessionDetail> = {},
): ChatSessionDetail {
    return {
        id: 's1',
        title: '朝の挨拶',
        config_name: 'friendly',
        message_count: messages.length,
        total_audio_bytes: 0,
        created_at: NOW,
        updated_at: NOW,
        messages,
        ...overrides,
    };
}

function listItem(
    overrides: Partial<ChatSessionListItem> = {},
): ChatSessionListItem {
    return {
        id: 's1',
        title: '朝の挨拶',
        config_name: 'friendly',
        message_count: 0,
        total_audio_bytes: 0,
        created_at: NOW,
        updated_at: NOW,
        ...overrides,
    };
}

function httpError(body: unknown, status: number): HTTPError {
    return new HTTPError(
        new Response(JSON.stringify(body), { status }),
        new Request('http://localhost/api/x'),
        {} as NormalizedOptions,
    );
}

function nextStreamMessage(stream: ControlledStream) {
    vi.mocked(api.streamMessage).mockImplementationOnce((_id, _content, opts) =>
        stream.generator(opts?.signal),
    );
}

function nextStreamEdit(stream: ControlledStream) {
    vi.mocked(api.streamEdit).mockImplementationOnce((_id, _msg, _c, opts) =>
        stream.generator(opts?.signal),
    );
}

/** 待っている非同期処理を進める。 */
async function flush() {
    await vi.advanceTimersByTimeAsync(0);
}

const state = () => useChatStore.getState();

/** 行がすべて元のオブジェクトへ戻っている（assistant-ui の変換キャッシュが効く）。 */
function expectSameObjects(before: readonly ChatUiMessage[]) {
    expect(state().messages).toHaveLength(before.length);
    before.forEach((message, index) => {
        expect(state().messages[index]).toBe(message);
    });
}

async function openSession(messages: readonly ChatSessionMessage[] = []) {
    vi.mocked(api.getSession).mockResolvedValueOnce(detail(messages));
    await state().openSession('s1');
}

const friendly = {
    name: 'friendly',
    display_name: 'フレンドリー',
    tts_enabled: false,
};
const voiced = { name: 'voiced', display_name: '音声あり', tts_enabled: true };

const savedTurn = {
    type: 'message',
    user: serverMessage({ id: 10, sequence: 0 }),
    assistant: assistantMessage({ id: 11, sequence: 1, content: '応答' }),
} as const;

describe('chat-store', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.clearAllMocks();
        vi.mocked(api.deleteSession).mockResolvedValue(undefined);
        URL.createObjectURL = vi.fn((blob: Blob) => `blob:${blob.size}`);
        URL.revokeObjectURL = vi.fn();
    });

    afterEach(() => {
        state().reset();
        localStorage.clear();
        vi.useRealTimers();
    });

    describe('sendMessage', () => {
        it('発話をすぐ表示して生成中にする。assistant の行はまだ作らない', async () => {
            await openSession();
            const stream = controlledStream();
            nextStreamMessage(stream);

            void state().sendMessage('こんにちは');

            expect(state().isRunning).toBe(true);
            expect(state().messages).toHaveLength(1);
            expect(state().messages[0]).toMatchObject({
                role: 'user',
                content: 'こんにちは',
                id: null,
            });
            expect(api.streamMessage).toHaveBeenCalledWith(
                's1',
                'こんにちは',
                expect.objectContaining({ signal: expect.any(AbortSignal) }),
            );
        });

        it('最初の delta で assistant の行を作り、次からは新しいオブジェクトで更新する', async () => {
            await openSession();
            const stream = controlledStream();
            nextStreamMessage(stream);
            void state().sendMessage('こんにちは');

            stream.push({ type: 'start' }, { type: 'delta', text: 'こん' });
            await flush();
            const first = state().messages[1];
            expect(first).toMatchObject({
                role: 'assistant',
                content: 'こん',
                uiStatus: 'streaming',
            });

            stream.push({ type: 'delta', text: 'にちは' });
            await flush();
            expect(state().messages[1].content).toBe('こんにちは');
            expect(state().messages[1]).not.toBe(first);
            expect(state().messages[1].localId).toBe(first.localId);
        });

        it('message で id を付け、localId は変えずに生成中を解く', async () => {
            await openSession();
            const stream = controlledStream();
            nextStreamMessage(stream);
            void state().sendMessage('こんにちは');
            stream.push({ type: 'delta', text: '応' });
            await flush();
            const [userBefore, assistantBefore] = state().messages;

            stream.push(savedTurn);
            await flush();

            expect(state().isRunning).toBe(false);
            expect(state().messages[0]).toMatchObject({
                localId: userBefore.localId,
                id: 10,
                sequence: 0,
                created_at: NOW,
            });
            expect(state().messages[1]).toMatchObject({
                localId: assistantBefore.localId,
                id: 11,
                content: '応答',
                uiStatus: 'complete',
            });
        });

        it('title で一覧とヘッダを更新し、done で集計を更新して一覧の先頭へ移す', async () => {
            vi.mocked(api.listSessions).mockResolvedValueOnce({
                count: 2,
                next: null,
                previous: null,
                results: [listItem({ id: 'other' }), listItem()],
            });
            await state().loadSessions();
            await openSession();
            const stream = controlledStream();
            nextStreamMessage(stream);
            void state().sendMessage('こんにちは');

            stream.push(savedTurn, { type: 'title', title: '新しい題' });
            await flush();
            expect(state().activeSession?.title).toBe('新しい題');
            expect(state().sessions[1].title).toBe('新しい題');

            stream.push({
                type: 'done',
                title: '新しい題',
                message_count: 2,
                total_audio_bytes: 2048,
                updated_at: LATER,
            });
            await flush();

            expect(state().sessions.map((s) => s.id)).toEqual(['s1', 'other']);
            expect(state().sessions[0]).toMatchObject({
                message_count: 2,
                total_audio_bytes: 2048,
                updated_at: LATER,
            });
        });

        it('生成中はもう 1 件を受け付けない', async () => {
            await openSession();
            nextStreamMessage(controlledStream());
            void state().sendMessage('1 件目');

            await expect(state().sendMessage('2 件目')).resolves.toBe(
                'not-sent',
            );

            expect(api.streamMessage).toHaveBeenCalledTimes(1);
            expect(state().messages).toHaveLength(1);
        });

        it('前のターンの音声合成を待っている間でも次を送れる', async () => {
            vi.mocked(api.fetchConfigs).mockResolvedValueOnce([friendly]);
            await state().loadConfigs();
            await openSession();
            const first = controlledStream();
            nextStreamMessage(first);
            void state().sendMessage('1 件目');
            first.push(savedTurn);
            await flush();

            const second = controlledStream();
            nextStreamMessage(second);
            void state().sendMessage('2 件目');
            await flush();

            expect(api.streamMessage).toHaveBeenCalledTimes(2);
            expect(state().isRunning).toBe(true);
            expect(state().messages.map((m) => m.content)).toEqual([
                'おはよう',
                '応答',
                '2 件目',
            ]);

            first.push({
                type: 'audio',
                message_id: 11,
                audio_url: '/a/11/',
                audio_format: 'wav',
                audio_size_bytes: 64,
            });
            await flush();

            expect(state().isRunning).toBe(true);
            expect(state().messages[1].audio_url).toBe('/a/11/');
        });
    });

    describe('音声', () => {
        async function startVoiced() {
            vi.mocked(api.fetchConfigs).mockResolvedValueOnce([voiced]);
            await state().loadConfigs();
            vi.mocked(api.getSession).mockResolvedValueOnce(
                detail([], { config_name: 'voiced' }),
            );
            await state().openSession('s1');
            const stream = controlledStream();
            nextStreamMessage(stream);
            void state().sendMessage('こんにちは');
            return stream;
        }

        it('音声が有効なプリセットでは message で合成中にする', async () => {
            const stream = await startVoiced();

            stream.push(savedTurn);
            await flush();

            expect(state().messages[1].audioState).toBe('pending');
        });

        it('audio で音声を付けて合成中を解く', async () => {
            const stream = await startVoiced();
            stream.push(savedTurn);

            stream.push({
                type: 'audio',
                message_id: 11,
                audio_url: '/a/11/',
                audio_format: 'wav',
                audio_size_bytes: 64,
            });
            await flush();

            expect(state().messages[1]).toMatchObject({
                audio_url: '/a/11/',
                audio_format: 'wav',
                audio_size_bytes: 64,
                audioState: 'idle',
            });
        });

        it('audio_error で失敗を記録する', async () => {
            const stream = await startVoiced();
            stream.push(savedTurn);

            stream.push({
                type: 'audio_error',
                message_id: 11,
                error: '合成に失敗しました',
            });
            await flush();

            expect(state().messages[1]).toMatchObject({
                audioState: 'failed',
                audioError: '合成に失敗しました',
            });
        });

        it('音声の通知がないまま done になれば合成中を解く', async () => {
            const stream = await startVoiced();
            stream.push(savedTurn, {
                type: 'done',
                title: '',
                message_count: 2,
                total_audio_bytes: 0,
                updated_at: LATER,
            });
            await flush();

            expect(state().messages[1].audioState).toBe('idle');
        });

        it('音声が無効なプリセットでは合成中にしない', async () => {
            vi.mocked(api.fetchConfigs).mockResolvedValueOnce([friendly]);
            await state().loadConfigs();
            await openSession();
            const stream = controlledStream();
            nextStreamMessage(stream);
            void state().sendMessage('こんにちは');

            stream.push(savedTurn);
            await flush();

            expect(state().messages[1].audioState).toBe('idle');
        });

        it('done の前に接続が切れたら合成中を解き、サーバーの値を読み直す', async () => {
            const stream = await startVoiced();
            stream.push(savedTurn);
            await flush();
            vi.mocked(api.getSession).mockResolvedValueOnce(
                detail(
                    [
                        savedTurn.user,
                        { ...savedTurn.assistant, audio_url: '/a/11/' },
                    ],
                    { config_name: 'voiced' },
                ),
            );

            stream.end();
            await flush();

            expect(state().isSyncing).toBe(false);
            expect(state().messages[1]).toMatchObject({
                audio_url: '/a/11/',
                audioState: 'idle',
            });
        });

        it('done の前に切れても読み直せなければ合成中を解くだけにする', async () => {
            const stream = await startVoiced();
            stream.push(savedTurn);
            await flush();
            vi.mocked(api.getSession).mockRejectedValueOnce(new Error('x'));

            stream.end();
            await flush();

            expect(state().messages[1]).toMatchObject({
                id: 11,
                audio_url: null,
                audioState: 'idle',
            });
            expect(state().error).toBeNull();
        });

        it('done の前に切れても次のターンの表示は巻き戻さない', async () => {
            const stream = await startVoiced();
            stream.push(savedTurn);
            await flush();
            nextStreamMessage(controlledStream());
            void state().sendMessage('次');
            vi.mocked(api.getSession).mockResolvedValueOnce(
                detail([savedTurn.user, savedTurn.assistant], {
                    config_name: 'voiced',
                }),
            );

            stream.end();
            await flush();

            expect(state().isRunning).toBe(true);
            expect(state().messages.at(-1)?.content).toBe('次');
        });
    });

    describe('送信の失敗', () => {
        const prior = [serverMessage(), assistantMessage()];

        it('error イベントなら発話を取り消し、サーバーの文言を出して not-sent を返す', async () => {
            await openSession(prior);
            const before = state().messages;
            const stream = controlledStream();
            nextStreamMessage(stream);
            const result = state().sendMessage('こんにちは');
            stream.push(
                { type: 'start' },
                { type: 'delta', text: '途中' },
                { type: 'error', status: 502, error: 'LLM に接続できません' },
            );

            await expect(result).resolves.toBe('not-sent');

            expectSameObjects(before);
            expect(state().isRunning).toBe(false);
            expect(state().error).toBe('LLM に接続できません');
        });

        it('HTTP エラーなら error の文言を出す', async () => {
            await openSession(prior);
            const before = state().messages;
            vi.mocked(api.streamMessage).mockImplementationOnce(
                // eslint-disable-next-line require-yield
                async function* () {
                    throw httpError({ error: '上限に達しました' }, 400);
                },
            );

            await expect(state().sendMessage('こんにちは')).resolves.toBe(
                'not-sent',
            );

            expectSameObjects(before);
            expect(state().error).toBe('上限に達しました');
        });

        it('スロットルの detail の文言を出す', async () => {
            await openSession(prior);
            vi.mocked(api.streamMessage).mockImplementationOnce(
                // eslint-disable-next-line require-yield
                async function* () {
                    throw httpError({ detail: '少し待ってください' }, 429);
                },
            );

            await state().sendMessage('こんにちは');

            expect(state().error).toBe('少し待ってください');
        });

        it('接続できなければ汎用の文言を出す', async () => {
            await openSession(prior);
            vi.mocked(api.streamMessage).mockImplementationOnce(
                // eslint-disable-next-line require-yield
                async function* () {
                    throw new TypeError('Failed to fetch');
                },
            );

            await expect(state().sendMessage('こんにちは')).resolves.toBe(
                'not-sent',
            );

            expect(state().error).toBe('応答の生成に失敗しました');
        });

        it('保存のあとの error イベントでは本文を残し、知らせるだけにする', async () => {
            await openSession(prior);
            const stream = controlledStream();
            nextStreamMessage(stream);
            const result = state().sendMessage('こんにちは');

            stream.push(savedTurn, {
                type: 'error',
                status: 502,
                error: '音声の保存に失敗しました',
            });
            stream.end();

            await expect(result).resolves.toBe('sent');
            expect(state().error).toBe('音声の保存に失敗しました');
            expect(state().messages.at(-1)?.id).toBe(11);
        });

        it('次の送信でエラーの表示を消す', async () => {
            await openSession(prior);
            vi.mocked(api.streamMessage).mockImplementationOnce(
                // eslint-disable-next-line require-yield
                async function* () {
                    throw new TypeError('Failed to fetch');
                },
            );
            await state().sendMessage('こんにちは');

            nextStreamMessage(controlledStream());
            void state().sendMessage('もう一度');

            expect(state().error).toBeNull();
        });
    });

    describe('新規チャット', () => {
        const created = detail([], { id: 'new', title: '' });

        async function ready() {
            vi.mocked(api.fetchConfigs).mockResolvedValueOnce([friendly]);
            await state().loadConfigs();
        }

        it('プリセットが選ばれていなければ送らない', async () => {
            await expect(state().sendMessage('こんにちは')).resolves.toBe(
                'not-sent',
            );

            expect(api.createSession).not.toHaveBeenCalled();
            expect(state().messages).toEqual([]);
        });

        it('発話を先に表示し、セッションを作ってから送信する', async () => {
            await ready();
            vi.mocked(api.createSession).mockResolvedValueOnce(created);
            nextStreamMessage(controlledStream());
            const onSessionCreated = vi.fn();

            void state().sendMessage('こんにちは', { onSessionCreated });
            expect(state().messages).toHaveLength(1);
            expect(state().isRunning).toBe(true);
            await flush();

            expect(api.createSession).toHaveBeenCalledWith('friendly');
            expect(onSessionCreated).toHaveBeenCalledWith('new');
            expect(state().activeSessionId).toBe('new');
            expect(state().sessions[0].id).toBe('new');
            expect(state().sessionsCount).toBe(1);
            expect(api.streamMessage).toHaveBeenCalledWith(
                'new',
                'こんにちは',
                expect.anything(),
            );
        });

        it('作成したばかりのセッションでは threadKey を変えない', async () => {
            await ready();
            vi.mocked(api.createSession).mockResolvedValueOnce(created);
            nextStreamMessage(controlledStream());
            const key = state().threadKey;

            void state().sendMessage('こんにちは');
            await flush();
            await state().openSession('new');

            expect(state().threadKey).toBe(key);
            expect(state().messages).toHaveLength(1);
        });

        it('セッションを作れなければ発話を取り消して文言を出す', async () => {
            await ready();
            vi.mocked(api.createSession).mockRejectedValueOnce(
                httpError({ error: '作成できません' }, 503),
            );

            await expect(state().sendMessage('こんにちは')).resolves.toBe(
                'not-sent',
            );

            expect(state().messages).toEqual([]);
            expect(state().isRunning).toBe(false);
            expect(state().error).toBe('作成できません');
        });

        it('応答に失敗したら作ったばかりの空セッションを消して元の画面へ戻す', async () => {
            await ready();
            vi.mocked(api.createSession).mockResolvedValueOnce(created);
            const stream = controlledStream();
            nextStreamMessage(stream);
            const onSessionAbandoned = vi.fn();
            const key = state().threadKey;

            const result = state().sendMessage('こんにちは', {
                onSessionAbandoned,
            });
            stream.push({ type: 'error', status: 502, error: '失敗' });

            await expect(result).resolves.toBe('not-sent');

            expect(api.deleteSession).toHaveBeenCalledWith('new');
            expect(onSessionAbandoned).toHaveBeenCalledTimes(1);
            expect(state().activeSessionId).toBeNull();
            expect(state().activeSession).toBeNull();
            expect(state().sessions).toEqual([]);
            expect(state().sessionsCount).toBe(0);
            expect(state().error).toBe('失敗');
            // composer を保つためリマウントさせない
            expect(state().threadKey).toBe(key);
        });

        it('セッションの作成中に停止したら作られたセッションを消して発話を戻す', async () => {
            await ready();
            vi.mocked(api.createSession).mockResolvedValueOnce(created);

            const result = state().sendMessage('こんにちは');
            state().cancelRun();
            expect(state().isRunning).toBe(false);
            expect(state().messages).toEqual([]);

            await expect(result).resolves.toBe('not-sent');

            expect(api.deleteSession).toHaveBeenCalledWith('new');
            expect(api.streamMessage).not.toHaveBeenCalled();
            expect(state().activeSessionId).toBeNull();
            expect(state().sessions).toEqual([]);
        });

        it('セッションの作成中に別のチャットへ移ったら作られたセッションを消す', async () => {
            await ready();
            vi.mocked(api.createSession).mockResolvedValueOnce(created);

            const result = state().sendMessage('こんにちは');
            vi.mocked(api.getSession).mockResolvedValueOnce(detail());
            await state().openSession('s1');
            await result;

            expect(api.deleteSession).toHaveBeenCalledWith('new');
            expect(api.streamMessage).not.toHaveBeenCalled();
            expect(state().activeSessionId).toBe('s1');
            expect(state().sessions).toEqual([]);
        });

        it('空セッションを消せなくても送信の失敗として扱う', async () => {
            await ready();
            vi.mocked(api.createSession).mockResolvedValueOnce(created);
            vi.mocked(api.deleteSession).mockRejectedValueOnce(new Error('x'));
            const stream = controlledStream();
            nextStreamMessage(stream);

            const result = state().sendMessage('こんにちは');
            stream.push({ type: 'error', status: 502, error: '失敗' });

            await expect(result).resolves.toBe('not-sent');
            expect(state().error).toBe('失敗');
        });
    });

    describe('停止と同期', () => {
        const prior = [serverMessage(), assistantMessage()];
        const stoppedUser = serverMessage({
            id: 3,
            sequence: 2,
            content: 'こんにちは',
        });
        const stoppedAssistant = assistantMessage({
            id: 4,
            sequence: 3,
            content: '途中まで',
        });

        async function startAndDelta() {
            await openSession(prior);
            const stream = controlledStream();
            nextStreamMessage(stream);
            const result = state().sendMessage('こんにちは');
            stream.push({ type: 'start' }, { type: 'delta', text: '途中' });
            await flush();
            return { stream, result };
        }

        it('停止すると読み取りを中断し、発話と途中の応答を残して同期中にする', async () => {
            const { stream } = await startAndDelta();
            vi.mocked(api.getSession).mockResolvedValue(detail(prior));

            state().cancelRun();

            expect(state().isRunning).toBe(false);
            expect(state().isSyncing).toBe(true);
            expect(state().messages.map((m) => m.content)).toEqual([
                'おはよう',
                'おはようございます',
                'こんにちは',
                '途中',
            ]);
            expect(state().messages[3].uiStatus).toBe('cancelled');
            await flush();
            expect(stream.isClosed()).toBe(true);
        });

        it('保存されるまで 500ms 間隔で確認し、localId を保ったままサーバーの値に揃える', async () => {
            const { result } = await startAndDelta();
            const localIds = state().messages.map((m) => m.localId);
            vi.mocked(api.getSession)
                .mockResolvedValueOnce(detail(prior))
                .mockResolvedValueOnce(detail(prior))
                .mockResolvedValueOnce(
                    detail([...prior, stoppedUser, stoppedAssistant]),
                );

            state().cancelRun();
            await flush();
            expect(state().isSyncing).toBe(true);
            await vi.advanceTimersByTimeAsync(500);
            expect(state().isSyncing).toBe(true);
            await vi.advanceTimersByTimeAsync(500);

            await expect(result).resolves.toBe('sent');
            expect(state().isSyncing).toBe(false);
            expect(state().error).toBeNull();
            expect(state().messages.map((m) => m.localId)).toEqual(localIds);
            expect(state().messages[3]).toMatchObject({
                id: 4,
                content: '途中まで',
                uiStatus: 'cancelled',
            });
        });

        it('本文が空で user だけ保存されても保存済みとして扱う', async () => {
            await openSession(prior);
            const stream = controlledStream();
            nextStreamMessage(stream);
            const result = state().sendMessage('こんにちは');
            await flush();
            vi.mocked(api.getSession).mockResolvedValueOnce(
                detail([...prior, stoppedUser]),
            );

            state().cancelRun();
            await flush();

            await expect(result).resolves.toBe('sent');
            expect(state().messages).toHaveLength(3);
            expect(state().messages[2].id).toBe(3);
        });

        it('同期が済んだら一覧の集計も更新する', async () => {
            vi.mocked(api.listSessions).mockResolvedValueOnce({
                count: 1,
                next: null,
                previous: null,
                results: [listItem({ message_count: 2 })],
            });
            await state().loadSessions();
            await startAndDelta();
            vi.mocked(api.getSession).mockResolvedValueOnce(
                detail([...prior, stoppedUser, stoppedAssistant]),
            );

            state().cancelRun();
            await flush();

            expect(state().sessions[0].message_count).toBe(4);
        });

        it('10 秒待っても保存されなければサーバーの値に戻し、バナーで知らせて入力へ戻す', async () => {
            const { result } = await startAndDelta();
            vi.mocked(api.getSession).mockResolvedValue(detail(prior));

            state().cancelRun();
            await vi.advanceTimersByTimeAsync(10_000);

            await expect(result).resolves.toBe('not-sent');
            expect(state().isSyncing).toBe(false);
            expect(state().messages.map((m) => m.content)).toEqual([
                'おはよう',
                'おはようございます',
            ]);
            expect(state().error).toContain('保存');
        });

        it('確認の GET が失敗しても再試行する', async () => {
            const { result } = await startAndDelta();
            vi.mocked(api.getSession)
                .mockRejectedValueOnce(new TypeError('Failed to fetch'))
                .mockResolvedValueOnce(
                    detail([...prior, stoppedUser, stoppedAssistant]),
                );

            state().cancelRun();
            await flush();
            expect(state().isSyncing).toBe(true);
            await vi.advanceTimersByTimeAsync(500);

            await expect(result).resolves.toBe('sent');
        });

        it('確認が 1 度も成功しなければ表示を保ったままバナーで知らせる', async () => {
            const { result } = await startAndDelta();
            vi.mocked(api.getSession).mockRejectedValue(
                new TypeError('Failed to fetch'),
            );

            state().cancelRun();
            await vi.advanceTimersByTimeAsync(10_000);

            await expect(result).resolves.toBe('sent');
            expect(state().isSyncing).toBe(false);
            expect(state().messages).toHaveLength(4);
            expect(state().error).not.toBeNull();
        });

        it('10 秒待ってもサーバーが別の内容のままならサーバーの値に揃えて知らせる', async () => {
            const { result } = await startAndDelta();
            const changed = [
                prior[0],
                { ...prior[1], content: '別のタブで変わった' },
            ];
            vi.mocked(api.getSession).mockResolvedValue(detail(changed));

            state().cancelRun();
            await vi.advanceTimersByTimeAsync(10_000);

            await expect(result).resolves.toBe('sent');
            expect(state().messages.map((m) => m.content)).toEqual([
                'おはよう',
                '別のタブで変わった',
            ]);
            expect(state().error).toContain('揃え');
        });

        it('同期中のセッションが消えていたら一覧から外して元の画面へ戻す', async () => {
            await openSession(prior);
            const stream = controlledStream();
            nextStreamMessage(stream);
            const onSessionAbandoned = vi.fn();
            const result = state().sendMessage('こんにちは', {
                onSessionAbandoned,
            });
            await flush();
            vi.mocked(api.getSession).mockRejectedValueOnce(
                httpError({ detail: 'not found' }, 404),
            );

            state().cancelRun();
            await flush();

            await expect(result).resolves.toBe('not-sent');
            expect(onSessionAbandoned).toHaveBeenCalledTimes(1);
            expect(state().activeSessionId).toBeNull();
        });

        it('同期中は送信できない', async () => {
            await startAndDelta();
            vi.mocked(api.getSession).mockResolvedValue(detail(prior));
            state().cancelRun();

            expect(selectIsSendDisabled(state())).toBe(true);
            await expect(state().sendMessage('次')).resolves.toBe('not-sent');
            expect(state().error).toBeNull();
        });

        it('同期中に別のチャットへ移ったら同期を打ち切る', async () => {
            await startAndDelta();
            vi.mocked(api.getSession).mockResolvedValueOnce(detail(prior));
            state().cancelRun();
            await flush();

            vi.mocked(api.getSession).mockClear();
            vi.mocked(api.getSession).mockResolvedValueOnce(
                detail([], { id: 'other' }),
            );
            await state().openSession('other');
            await vi.advanceTimersByTimeAsync(10_000);

            expect(api.getSession).toHaveBeenCalledTimes(1);
            expect(state().isSyncing).toBe(false);
            expect(state().messages).toEqual([]);
            expect(state().error).toBeNull();
        });

        it('終端イベントなしで接続が切れても同じように同期する', async () => {
            const { stream, result } = await startAndDelta();
            vi.mocked(api.getSession).mockResolvedValueOnce(
                detail([...prior, stoppedUser, stoppedAssistant]),
            );

            stream.end();
            await flush();

            await expect(result).resolves.toBe('sent');
            expect(state().isRunning).toBe(false);
            expect(state().messages[3]).toMatchObject({
                id: 4,
                content: '途中まで',
            });
        });

        it('読み取りの途中で例外になっても発話を取り消さずに同期する', async () => {
            const { stream, result } = await startAndDelta();
            vi.mocked(api.getSession).mockResolvedValueOnce(
                detail([...prior, stoppedUser, stoppedAssistant]),
            );

            stream.fail(new TypeError('network error'));
            await flush();

            await expect(result).resolves.toBe('sent');
            expect(state().messages).toHaveLength(4);
        });

        it('作ったばかりのセッションで何も保存されなければ空セッションを消す', async () => {
            vi.mocked(api.fetchConfigs).mockResolvedValueOnce([friendly]);
            await state().loadConfigs();
            vi.mocked(api.createSession).mockResolvedValueOnce(
                detail([], { id: 'new' }),
            );
            const stream = controlledStream();
            nextStreamMessage(stream);
            const onSessionAbandoned = vi.fn();
            const result = state().sendMessage('こんにちは', {
                onSessionAbandoned,
            });
            await flush();
            vi.mocked(api.getSession).mockResolvedValue(
                detail([], { id: 'new' }),
            );

            state().cancelRun();
            await vi.advanceTimersByTimeAsync(10_000);

            await expect(result).resolves.toBe('not-sent');
            expect(api.deleteSession).toHaveBeenCalledWith('new');
            expect(onSessionAbandoned).toHaveBeenCalledTimes(1);
            expect(state().activeSessionId).toBeNull();
            expect(state().messages).toEqual([]);
        });

        it('生成中でなければ cancelRun は何もしない', async () => {
            await openSession(prior);

            state().cancelRun();

            expect(state().isSyncing).toBe(false);
        });
    });

    describe('editMessage', () => {
        const prior = [
            serverMessage({ id: 1, sequence: 0 }),
            assistantMessage({ id: 2, sequence: 1 }),
            serverMessage({ id: 3, sequence: 2, content: '2 回目' }),
            assistantMessage({ id: 4, sequence: 3, content: '2 回目の応答' }),
        ];
        const edited = serverMessage({
            id: 5,
            sequence: 2,
            content: '直した',
        });
        const editedReply = assistantMessage({
            id: 6,
            sequence: 3,
            content: '新しい応答',
        });

        it('対象の本文を差し替えて以降を落とし、サーバー id で API を呼ぶ', async () => {
            await openSession(prior);
            nextStreamEdit(controlledStream());
            const target = state().messages[2];

            void state().editMessage(target.localId, '直した');

            expect(state().isRunning).toBe(true);
            expect(state().messages).toHaveLength(3);
            expect(state().messages[2]).toMatchObject({
                localId: target.localId,
                id: 3,
                content: '直した',
            });
            expect(api.streamEdit).toHaveBeenCalledWith(
                's1',
                3,
                '直した',
                expect.objectContaining({ signal: expect.any(AbortSignal) }),
            );
        });

        it('message で新しい id を付け、localId は変えない', async () => {
            await openSession(prior);
            const stream = controlledStream();
            nextStreamEdit(stream);
            const target = state().messages[2];
            void state().editMessage(target.localId, '直した');

            stream.push(
                { type: 'delta', text: '新' },
                { type: 'message', user: edited, assistant: editedReply },
            );
            await flush();

            expect(state().isRunning).toBe(false);
            expect(state().messages).toHaveLength(4);
            expect(state().messages[2]).toMatchObject({
                localId: target.localId,
                id: 5,
            });
            expect(state().messages[3]).toMatchObject({
                id: 6,
                content: '新しい応答',
            });
        });

        it('失敗したら元のオブジェクトの配列へ戻して not-sent を返す', async () => {
            await openSession(prior);
            const before = state().messages;
            const stream = controlledStream();
            nextStreamEdit(stream);
            const result = state().editMessage(before[2].localId, '直した');
            stream.push({ type: 'error', status: 502, error: '失敗しました' });

            await expect(result).resolves.toBe('not-sent');

            expectSameObjects(before);
            expect(state().messages[2]).toBe(before[2]);
            expect(state().error).toBe('失敗しました');
        });

        it('保存前の行は編集できない', async () => {
            await openSession(prior);
            nextStreamMessage(controlledStream());
            void state().sendMessage('未保存');
            const unsaved = state().messages[4];
            state().cancelRun();
            vi.mocked(api.getSession).mockRejectedValue(new TypeError('x'));
            await vi.advanceTimersByTimeAsync(10_000);

            await expect(
                state().editMessage(unsaved.localId, '直した'),
            ).resolves.toBe('not-sent');

            expect(api.streamEdit).not.toHaveBeenCalled();
            expect(state().error).not.toBeNull();
        });

        it('同期中は編集を受け付けない', async () => {
            await openSession(prior);
            const stream = controlledStream();
            nextStreamMessage(stream);
            void state().sendMessage('次');
            await flush();
            vi.mocked(api.getSession).mockResolvedValue(detail(prior));
            state().cancelRun();
            const target = state().messages[2];

            await expect(
                state().editMessage(target.localId, '直した'),
            ).resolves.toBe('not-sent');

            expect(api.streamEdit).not.toHaveBeenCalled();
        });

        it('停止すると対象の行の id が変わるまで同期する', async () => {
            await openSession(prior);
            const stream = controlledStream();
            nextStreamEdit(stream);
            const target = state().messages[2];
            const result = state().editMessage(target.localId, '直した');
            stream.push({ type: 'delta', text: '途' });
            await flush();
            vi.mocked(api.getSession)
                .mockResolvedValueOnce(detail(prior))
                .mockResolvedValueOnce(
                    detail([prior[0], prior[1], edited, editedReply]),
                );

            state().cancelRun();
            await flush();
            expect(state().isSyncing).toBe(true);
            await vi.advanceTimersByTimeAsync(500);

            await expect(result).resolves.toBe('sent');
            expect(state().messages[2]).toMatchObject({
                localId: target.localId,
                id: 5,
                content: '直した',
            });
            expect(state().messages[3].content).toBe('新しい応答');
        });

        it('停止しても何も変わらなければ元のオブジェクトへ戻して not-sent を返す', async () => {
            await openSession(prior);
            const before = state().messages;
            const stream = controlledStream();
            nextStreamEdit(stream);
            const result = state().editMessage(before[2].localId, '直した');
            await flush();
            vi.mocked(api.getSession).mockResolvedValue(detail(prior));

            state().cancelRun();
            await vi.advanceTimersByTimeAsync(10_000);

            await expect(result).resolves.toBe('not-sent');
            expectSameObjects(before);
        });

        it('置き換えが保存されたら、消えた行の音声の Object URL を解放する', async () => {
            const withAudio = [
                prior[0],
                prior[1],
                prior[2],
                { ...prior[3], audio_url: '/a/4/', audio_size_bytes: 8 },
            ];
            await openSession(withAudio);
            vi.mocked(api.fetchAudioBlob).mockResolvedValueOnce(
                new Blob(['x']),
            );
            await state().ensureAudioObjectUrl(4);
            const stream = controlledStream();
            nextStreamEdit(stream);
            void state().editMessage(state().messages[2].localId, '直した');
            await flush();
            expect(URL.revokeObjectURL).not.toHaveBeenCalled();

            stream.push({
                type: 'message',
                user: edited,
                assistant: editedReply,
            });
            await flush();

            expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:1');
            expect(state().audioObjectUrls.has(4)).toBe(false);
            expect(state().audioBlobs.has(4)).toBe(false);
        });
    });

    describe('regenerate', () => {
        const prior = [serverMessage(), assistantMessage()];

        it('同じ本文で編集 API を呼び、応答を落とす', async () => {
            await openSession(prior);
            nextStreamEdit(controlledStream());
            const user = state().messages[0];

            void state().regenerate(user.localId);

            expect(api.streamEdit).toHaveBeenCalledWith(
                's1',
                1,
                'おはよう',
                expect.anything(),
            );
            expect(state().messages).toHaveLength(1);
            expect(state().isRunning).toBe(true);
        });

        it('失敗したら元の表示へ戻してバナーを出す', async () => {
            await openSession(prior);
            const before = state().messages;
            const stream = controlledStream();
            nextStreamEdit(stream);

            const result = state().regenerate(before[0].localId);
            stream.push({ type: 'error', status: 504, error: 'タイムアウト' });
            await flush();
            await result;

            expectSameObjects(before);
            expect(state().error).toBe('タイムアウト');
        });

        it('知らない行なら何もしない', async () => {
            await openSession(prior);

            await state().regenerate('local-unknown');

            expect(api.streamEdit).not.toHaveBeenCalled();
        });
    });

    describe('セッションの切り替え', () => {
        const prior = [serverMessage(), assistantMessage()];

        it('詳細を読み込んで表示し、threadKey を変える', async () => {
            const key = state().threadKey;
            vi.mocked(api.getSession).mockResolvedValueOnce(detail(prior));

            const pending = state().openSession('s1');
            expect(state().isLoadingDetail).toBe(true);
            expect(state().threadKey).not.toBe(key);

            await expect(pending).resolves.toBe('ok');
            expect(state().isLoadingDetail).toBe(false);
            expect(state().activeSession?.title).toBe('朝の挨拶');
            expect(state().messages[0].localId).toBe('srv-1');
        });

        it('表示中のセッションなら読み直さない', async () => {
            await openSession(prior);
            const key = state().threadKey;

            await expect(state().openSession('s1')).resolves.toBe('ok');

            expect(api.getSession).toHaveBeenCalledTimes(1);
            expect(state().threadKey).toBe(key);
        });

        it('見つからなければ not-found を返して状態を戻す', async () => {
            vi.mocked(api.getSession).mockRejectedValueOnce(
                httpError({ detail: 'not found' }, 404),
            );

            await expect(state().openSession('gone')).resolves.toBe(
                'not-found',
            );

            expect(state().activeSessionId).toBeNull();
            expect(state().isLoadingDetail).toBe(false);
        });

        it('読み込みに失敗したらバナーを出す', async () => {
            vi.mocked(api.getSession).mockRejectedValueOnce(
                new TypeError('Failed to fetch'),
            );

            await expect(state().openSession('s1')).resolves.toBe('error');

            expect(state().error).toBe('チャットの読み込みに失敗しました');
            expect(state().isLoadingDetail).toBe(false);
        });

        it('古い読み込みの結果で新しいセッションを上書きしない', async () => {
            let resolveFirst: (value: ChatSessionDetail) => void = () => {};
            vi.mocked(api.getSession).mockImplementationOnce(
                () =>
                    new Promise((resolve) => {
                        resolveFirst = resolve;
                    }),
            );
            const first = state().openSession('a');
            vi.mocked(api.getSession).mockResolvedValueOnce(
                detail([], { id: 'b', title: 'B' }),
            );
            await state().openSession('b');

            resolveFirst(detail(prior, { id: 'a', title: 'A' }));

            await expect(first).resolves.toBe('stale');
            expect(state().activeSession?.title).toBe('B');
            expect(state().messages).toEqual([]);
        });

        it('生成中に切り替えると中断し、古い応答で別のセッションを上書きしない', async () => {
            await openSession(prior);
            const stream = controlledStream();
            nextStreamMessage(stream);
            void state().sendMessage('こんにちは');
            stream.push({ type: 'delta', text: '途中' });
            await flush();

            vi.mocked(api.getSession).mockResolvedValueOnce(
                detail([], { id: 'other' }),
            );
            await state().openSession('other');
            stream.push({ type: 'delta', text: '遅れて届いた' }, savedTurn);
            await flush();

            expect(stream.isClosed()).toBe(true);
            expect(state().isRunning).toBe(false);
            expect(state().isSyncing).toBe(false);
            expect(state().messages).toEqual([]);
            expect(api.getSession).toHaveBeenCalledWith('other');
        });

        it('切り替えのあと音声合成の結果が届いても別のセッションに反映しない。題は一覧に反映する', async () => {
            vi.mocked(api.listSessions).mockResolvedValueOnce({
                count: 2,
                next: null,
                previous: null,
                results: [listItem(), listItem({ id: 'other', title: '別' })],
            });
            await state().loadSessions();
            await openSession(prior);
            const stream = controlledStream();
            nextStreamMessage(stream);
            void state().sendMessage('こんにちは');
            stream.push(savedTurn);
            await flush();

            const others = [
                serverMessage({ id: 11, content: '同じ id の別の行' }),
            ];
            vi.mocked(api.getSession).mockResolvedValueOnce(
                detail(others, { id: 'other', title: '別' }),
            );
            await state().openSession('other');
            stream.push(
                {
                    type: 'audio',
                    message_id: 11,
                    audio_url: '/a/11/',
                    audio_format: 'wav',
                    audio_size_bytes: 64,
                },
                { type: 'title', title: '新しい題' },
            );
            await flush();

            expect(stream.isClosed()).toBe(false);
            expect(state().messages[0].audio_url).toBeNull();
            expect(state().activeSession?.title).toBe('別');
            expect(state().sessions.find((s) => s.id === 's1')?.title).toBe(
                '新しい題',
            );
        });

        it('切り替えると音声のキャッシュを解放する', async () => {
            await openSession([
                prior[0],
                { ...prior[1], audio_url: '/a/2/', audio_size_bytes: 8 },
            ]);
            vi.mocked(api.fetchAudioBlob).mockResolvedValueOnce(
                new Blob(['x']),
            );
            await state().ensureAudioObjectUrl(2);

            vi.mocked(api.getSession).mockResolvedValueOnce(
                detail([], { id: 'other' }),
            );
            await state().openSession('other');

            expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:1');
            expect(state().audioObjectUrls.size).toBe(0);
        });

        it('新しいチャットへ移ると表示を空にして threadKey を変える', async () => {
            await openSession(prior);
            const key = state().threadKey;

            state().startNewChat();

            expect(state().activeSessionId).toBeNull();
            expect(state().activeSession).toBeNull();
            expect(state().messages).toEqual([]);
            expect(state().threadKey).not.toBe(key);
        });

        it('すでに新しいチャットなら threadKey を変えない', () => {
            const key = state().threadKey;

            state().startNewChat();

            expect(state().threadKey).toBe(key);
        });

        it('読み込み中に新しいチャットへ移ると読み込みの結果を捨てる', async () => {
            let resolve: (value: ChatSessionDetail) => void = () => {};
            vi.mocked(api.getSession).mockImplementationOnce(
                () =>
                    new Promise((r) => {
                        resolve = r;
                    }),
            );
            const pending = state().openSession('s1');

            state().startNewChat();
            resolve(detail(prior));

            await expect(pending).resolves.toBe('stale');
            expect(state().messages).toEqual([]);
            expect(state().isLoadingDetail).toBe(false);
        });
    });

    describe('セッション一覧', () => {
        it('一覧を読み込む', async () => {
            vi.mocked(api.listSessions).mockResolvedValueOnce({
                count: 3,
                next: 'x',
                previous: null,
                results: [listItem()],
            });

            await state().loadSessions();

            expect(api.listSessions).toHaveBeenCalledWith({
                limit: 20,
                offset: 0,
            });
            expect(state().sessions).toHaveLength(1);
            expect(state().sessionsCount).toBe(3);
            expect(state().hasMoreSessions).toBe(true);
        });

        it('続きを読み込むと末尾へ足し、重複を除く', async () => {
            vi.mocked(api.listSessions)
                .mockResolvedValueOnce({
                    count: 3,
                    next: 'x',
                    previous: null,
                    results: [listItem({ id: 'a' }), listItem({ id: 'b' })],
                })
                .mockResolvedValueOnce({
                    count: 3,
                    next: null,
                    previous: null,
                    results: [listItem({ id: 'b' }), listItem({ id: 'c' })],
                });
            await state().loadSessions();

            await state().loadMoreSessions();

            expect(api.listSessions).toHaveBeenLastCalledWith({
                limit: 20,
                offset: 2,
            });
            expect(state().sessions.map((s) => s.id)).toEqual(['a', 'b', 'c']);
            expect(state().hasMoreSessions).toBe(false);
        });

        it('続きがなければ読み込まない', async () => {
            await state().loadMoreSessions();

            expect(api.listSessions).not.toHaveBeenCalled();
        });

        it('画面を離れたあとに届いた一覧と設定は捨てる', async () => {
            let resolveList: (value: never) => void = () => {};
            let resolveConfigs: (value: GenerateConfig[]) => void = () => {};
            vi.mocked(api.listSessions).mockImplementationOnce(
                () =>
                    new Promise((resolve) => {
                        resolveList = resolve as (value: never) => void;
                    }),
            );
            vi.mocked(api.fetchConfigs).mockImplementationOnce(
                () =>
                    new Promise((resolve) => {
                        resolveConfigs = resolve;
                    }),
            );
            const list = state().loadSessions();
            const configs = state().loadConfigs();

            state().reset();
            resolveList({
                count: 1,
                next: null,
                previous: null,
                results: [listItem()],
            } as never);
            resolveConfigs([friendly]);
            await Promise.all([list, configs]);

            expect(state().sessions).toEqual([]);
            expect(state().configs).toEqual([]);
        });

        it('読み込みに失敗したらバナーを出す', async () => {
            vi.mocked(api.listSessions).mockRejectedValueOnce(new Error('x'));

            await state().loadSessions();

            expect(state().error).toBe('セッション一覧の取得に失敗しました');
            expect(state().isLoadingList).toBe(false);
        });

        it('表示中のセッションの題を変えると一覧にも反映する', async () => {
            vi.mocked(api.listSessions).mockResolvedValueOnce({
                count: 1,
                next: null,
                previous: null,
                results: [listItem()],
            });
            await state().loadSessions();
            await openSession([serverMessage()]);
            vi.mocked(api.updateSessionTitle).mockResolvedValueOnce(
                detail([serverMessage()], { title: '新しい題' }),
            );

            await state().updateActiveTitle('新しい題');

            expect(api.updateSessionTitle).toHaveBeenCalledWith(
                's1',
                '新しい題',
            );
            expect(state().activeSession?.title).toBe('新しい題');
            expect(state().sessions[0].title).toBe('新しい題');
        });

        it('表示中のセッションがなければ題を変えない', async () => {
            await state().updateActiveTitle('新しい題');

            expect(api.updateSessionTitle).not.toHaveBeenCalled();
        });

        it('題を変えられなければ元の題のままバナーで知らせる', async () => {
            await openSession([serverMessage()]);
            vi.mocked(api.updateSessionTitle).mockRejectedValueOnce(
                new Error('x'),
            );

            await state().updateActiveTitle('新しい題');

            expect(state().activeSession?.title).toBe('朝の挨拶');
            expect(state().error).toBe('タイトルを変更できませんでした');
        });

        it('セッションを消すと一覧から外す。表示中でなければ表示はそのまま', async () => {
            vi.mocked(api.listSessions).mockResolvedValueOnce({
                count: 2,
                next: null,
                previous: null,
                results: [listItem(), listItem({ id: 'other' })],
            });
            await state().loadSessions();
            await openSession([serverMessage()]);

            await state().removeSession('other');

            expect(api.deleteSession).toHaveBeenCalledWith('other');
            expect(state().sessions.map((s) => s.id)).toEqual(['s1']);
            expect(state().sessionsCount).toBe(1);
            expect(state().activeSessionId).toBe('s1');
            expect(state().messages).toHaveLength(1);
        });

        it('表示中のセッションを消すと表示を空にして中断する', async () => {
            await openSession([serverMessage()]);
            const stream = controlledStream();
            nextStreamMessage(stream);
            void state().sendMessage('こんにちは');
            const key = state().threadKey;

            await state().removeSession('s1');
            await flush();

            expect(stream.isClosed()).toBe(true);
            expect(state().activeSessionId).toBeNull();
            expect(state().messages).toEqual([]);
            expect(state().isRunning).toBe(false);
            expect(state().threadKey).not.toBe(key);
        });

        it('音声合成を待っているセッションを消すと読み取りをやめる', async () => {
            await openSession();
            const stream = controlledStream();
            nextStreamMessage(stream);
            void state().sendMessage('こんにちは');
            stream.push(savedTurn);
            await flush();
            vi.mocked(api.getSession).mockResolvedValueOnce(
                detail([], { id: 'other' }),
            );
            await state().openSession('other');

            await state().removeSession('s1');
            await flush();

            expect(stream.isClosed()).toBe(true);
            expect(state().activeSessionId).toBe('other');
        });
    });

    describe('プリセット', () => {
        it('既定は先頭のプリセット', async () => {
            vi.mocked(api.fetchConfigs).mockResolvedValueOnce([
                friendly,
                voiced,
            ]);

            await state().loadConfigs();

            expect(state().configs).toEqual([friendly, voiced]);
            expect(state().selectedConfigName).toBe('friendly');
        });

        it('前回の選択を覚えている', async () => {
            vi.mocked(api.fetchConfigs).mockResolvedValue([friendly, voiced]);
            await state().loadConfigs();

            state().selectConfig('voiced');
            state().reset();
            await state().loadConfigs();

            expect(state().selectedConfigName).toBe('voiced');
        });

        it('覚えているプリセットがなくなっていれば先頭を選ぶ', async () => {
            localStorage.setItem('talk-selected-config', 'gone');
            vi.mocked(api.fetchConfigs).mockResolvedValueOnce([friendly]);

            await state().loadConfigs();

            expect(state().selectedConfigName).toBe('friendly');
        });

        it('localStorage が使えなくても動く', async () => {
            const getItem = vi
                .spyOn(Storage.prototype, 'getItem')
                .mockImplementation(() => {
                    throw new Error('blocked');
                });
            const setItem = vi
                .spyOn(Storage.prototype, 'setItem')
                .mockImplementation(() => {
                    throw new Error('blocked');
                });
            vi.mocked(api.fetchConfigs).mockResolvedValueOnce([friendly]);

            await state().loadConfigs();
            state().selectConfig('friendly');

            expect(state().selectedConfigName).toBe('friendly');
            getItem.mockRestore();
            setItem.mockRestore();
        });

        it('取得に失敗したら記録する', async () => {
            vi.mocked(api.fetchConfigs).mockRejectedValueOnce(new Error('x'));

            await state().loadConfigs();

            expect(state().configsFailed).toBe(true);
            expect(state().selectedConfigName).toBeNull();
        });

        it('プリセットがなければ選ばない', async () => {
            vi.mocked(api.fetchConfigs).mockResolvedValueOnce([]);

            await state().loadConfigs();

            expect(state().selectedConfigName).toBeNull();
        });
    });

    describe('音声のキャッシュと削除', () => {
        const withAudio = [
            serverMessage(),
            assistantMessage({ audio_url: '/a/2/', audio_size_bytes: 8 }),
            serverMessage({ id: 3, sequence: 2 }),
            assistantMessage({
                id: 4,
                sequence: 3,
                audio_url: '/a/4/',
                audio_size_bytes: 8,
            }),
        ];

        it('同じ音声は 1 度だけ取得する', async () => {
            await openSession(withAudio);
            vi.mocked(api.fetchAudioBlob).mockResolvedValue(new Blob(['x']));

            const [a, b] = await Promise.all([
                state().ensureAudioObjectUrl(2),
                state().ensureAudioObjectUrl(2),
            ]);
            const c = await state().ensureAudioObjectUrl(2);

            expect(a).toBe('blob:1');
            expect(b).toBe('blob:1');
            expect(c).toBe('blob:1');
            expect(api.fetchAudioBlob).toHaveBeenCalledTimes(1);
            expect(state().audioBlobs.get(2)).toBeInstanceOf(Blob);
        });

        it('表示中のセッションがなければ取得しない', async () => {
            await expect(state().ensureAudioObjectUrl(2)).resolves.toBeNull();

            expect(api.fetchAudioBlob).not.toHaveBeenCalled();
        });

        it('取得の間にセッションを切り替えたらキャッシュせずに解放する', async () => {
            await openSession(withAudio);
            let resolve: (value: Blob) => void = () => {};
            vi.mocked(api.fetchAudioBlob).mockImplementationOnce(
                () =>
                    new Promise((r) => {
                        resolve = r;
                    }),
            );
            const pending = state().ensureAudioObjectUrl(2);
            vi.mocked(api.getSession).mockResolvedValueOnce(
                detail([], { id: 'other' }),
            );
            await state().openSession('other');

            resolve(new Blob(['x']));

            await expect(pending).resolves.toBeNull();
            expect(state().audioObjectUrls.size).toBe(0);
        });

        it('取得に失敗したら次は取り直せる', async () => {
            await openSession(withAudio);
            vi.mocked(api.fetchAudioBlob)
                .mockRejectedValueOnce(new Error('x'))
                .mockResolvedValueOnce(new Blob(['x']));

            await expect(state().ensureAudioObjectUrl(2)).rejects.toThrow('x');

            await expect(state().ensureAudioObjectUrl(2)).resolves.toBe(
                'blob:1',
            );
        });

        it('1 件の音声を消すと本文を残して音声の情報だけ消す', async () => {
            vi.mocked(api.listSessions).mockResolvedValueOnce({
                count: 1,
                next: null,
                previous: null,
                results: [listItem({ total_audio_bytes: 16 })],
            });
            await state().loadSessions();
            await openSession(withAudio);
            vi.mocked(api.fetchAudioBlob).mockResolvedValueOnce(
                new Blob(['x']),
            );
            await state().ensureAudioObjectUrl(2);
            vi.mocked(api.deleteAudio).mockResolvedValueOnce(undefined);

            await state().deleteMessageAudio(2);

            expect(api.deleteAudio).toHaveBeenCalledWith('s1', 2);
            expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:1');
            expect(state().audioObjectUrls.has(2)).toBe(false);
            expect(state().messages[1]).toMatchObject({
                content: 'おはようございます',
                audio_url: null,
            });
            expect(state().messages[3].audio_url).toBe('/a/4/');
            expect(state().sessions[0].total_audio_bytes).toBe(8);
        });

        it('表示中のセッションがなければ音声を消さない', async () => {
            await state().deleteMessageAudio(2);
            await state().deleteAllAudio();

            expect(api.deleteAudio).not.toHaveBeenCalled();
            expect(api.bulkDeleteAudio).not.toHaveBeenCalled();
        });

        it('音声を消せなければ表示を変えずにバナーで知らせる', async () => {
            await openSession(withAudio);
            vi.mocked(api.deleteAudio).mockRejectedValueOnce(new Error('x'));
            vi.mocked(api.bulkDeleteAudio).mockRejectedValueOnce(
                new Error('x'),
            );

            await state().deleteMessageAudio(2);
            expect(state().error).toBe('音声を削除できませんでした');
            state().clearError();
            await state().deleteAllAudio();

            expect(state().error).toBe('音声を削除できませんでした');
            expect(state().messages[1].audio_url).toBe('/a/2/');
        });

        it('音声を一括で消す', async () => {
            vi.mocked(api.listSessions).mockResolvedValueOnce({
                count: 1,
                next: null,
                previous: null,
                results: [listItem({ total_audio_bytes: 16 })],
            });
            await state().loadSessions();
            await openSession(withAudio);
            vi.mocked(api.fetchAudioBlob).mockResolvedValueOnce(
                new Blob(['x']),
            );
            await state().ensureAudioObjectUrl(2);
            vi.mocked(api.bulkDeleteAudio).mockResolvedValueOnce(undefined);

            await state().deleteAllAudio();

            expect(api.bulkDeleteAudio).toHaveBeenCalledWith('s1');
            expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:1');
            expect(state().audioObjectUrls.size).toBe(0);
            expect(state().messages.every((m) => m.audio_url === null)).toBe(
                true,
            );
            expect(state().sessions[0].total_audio_bytes).toBe(0);
        });
    });

    describe('selectIsSendDisabled / selectIsAtMessageLimit', () => {
        const fifty = Array.from({ length: 50 }, (_, i) =>
            serverMessage({
                id: i + 1,
                sequence: i,
                role: i % 2 === 0 ? 'user' : 'assistant',
            }),
        );

        it('新規チャットではプリセットが選ばれるまで送信できない', async () => {
            expect(selectIsSendDisabled(state())).toBe(true);

            vi.mocked(api.fetchConfigs).mockResolvedValueOnce([friendly]);
            await state().loadConfigs();

            expect(selectIsSendDisabled(state())).toBe(false);
        });

        it('読み込み中は送信できない', () => {
            vi.mocked(api.getSession).mockImplementationOnce(
                () => new Promise(() => {}),
            );
            void state().openSession('s1');

            expect(selectIsSendDisabled(state())).toBe(true);
        });

        it('50 件に達すると上限として送信できない', async () => {
            await openSession(fifty);

            expect(selectIsAtMessageLimit(state())).toBe(true);
            expect(selectIsSendDisabled(state())).toBe(true);
        });

        it('49 件までは送信できる', async () => {
            await openSession(fifty.slice(0, 49));

            expect(selectIsAtMessageLimit(state())).toBe(false);
            expect(selectIsSendDisabled(state())).toBe(false);
        });
    });

    describe('reset', () => {
        it('中断して初期状態へ戻す。音声合成の待ちも止める', async () => {
            await openSession();
            const stream = controlledStream();
            nextStreamMessage(stream);
            void state().sendMessage('こんにちは');
            stream.push(savedTurn);
            await flush();
            const running = controlledStream();
            nextStreamMessage(running);
            void state().sendMessage('次');
            await flush();

            state().reset();
            await flush();

            expect(stream.isClosed()).toBe(true);
            expect(running.isClosed()).toBe(true);
            expect(state().activeSessionId).toBeNull();
            expect(state().messages).toEqual([]);
            expect(state().isRunning).toBe(false);
        });

        it('clearError でバナーを消す', async () => {
            vi.mocked(api.listSessions).mockRejectedValueOnce(new Error('x'));
            await state().loadSessions();

            state().clearError();

            expect(state().error).toBeNull();
        });
    });
});
