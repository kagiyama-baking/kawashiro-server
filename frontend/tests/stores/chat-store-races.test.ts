import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '@/lib/api/talk';
import {
    selectHasLoadFailed,
    selectIsSendDisabled,
    useChatStore,
} from '@/stores/chat-store';
import type { ChatSessionDetail } from '@/types/talk';
import {
    assistantMessage,
    deferred,
    httpError,
    NOW,
    sessionDetail,
    sessionItem,
    userMessage,
} from '../helpers/chat-fixtures';
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
    fetchSettings: vi.fn(),
    getSession: vi.fn(),
    listSessions: vi.fn(),
    streamEdit: vi.fn(),
    streamMessage: vi.fn(),
    updateSessionTitle: vi.fn(),
}));

const state = () => useChatStore.getState();
const flush = () => vi.advanceTimersByTimeAsync(0);

const voiced = { id: 2, name: '音声あり', tts_enabled: true, skills: [] };

function nextStreamMessage(stream: ControlledStream) {
    vi.mocked(api.streamMessage).mockImplementationOnce((_id, _c, opts) =>
        stream.generator(opts?.signal),
    );
}

function nextStreamEdit(stream: ControlledStream) {
    vi.mocked(api.streamEdit).mockImplementationOnce((_id, _msg, _c, opts) =>
        stream.generator(opts?.signal),
    );
}

async function openSession(
    id = 's1',
    messages: ChatSessionDetail['messages'] = [],
    overrides: Partial<ChatSessionDetail> = {},
) {
    vi.mocked(api.getSession).mockResolvedValueOnce(
        sessionDetail(messages, { id, ...overrides }),
    );
    await state().openSession(id);
}

const savedTurn = {
    type: 'message',
    user: userMessage({ id: 10, sequence: 0, content: 'こんにちは' }),
    assistant: assistantMessage({ id: 11, sequence: 1, content: '応答' }),
} as const;

const doneEvent = {
    type: 'done',
    title: '朝の挨拶',
    message_count: 2,
    total_audio_bytes: 8,
    updated_at: NOW,
} as const;

describe('chat-store の競合と異常系', () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.resetAllMocks();
        vi.mocked(api.deleteSession).mockResolvedValue(undefined);
        URL.createObjectURL = vi.fn((blob: Blob) => `blob:${blob.size}`);
        URL.revokeObjectURL = vi.fn();
    });

    afterEach(() => {
        state().reset();
        vi.useRealTimers();
    });

    describe('URL の id', () => {
        // react-router は %2F を / に戻すので、細工したリンクで別の API を呼ばれてしまう
        it.each([
            '../../hn-agent/run-all/?',
            '..',
            'a/b',
            'a?b',
            'a%2Fb',
            'a b',
        ])(
            'パスに入れられない id（%s）は API を呼ばずに not-found にする',
            async (id) => {
                await expect(state().openSession(id)).resolves.toBe(
                    'not-found',
                );

                expect(api.getSession).not.toHaveBeenCalled();
                expect(state().activeSessionId).toBeNull();
                expect(state().error).toBe('チャットが見つかりませんでした');
            },
        );

        it('UUID の id は読み込む', async () => {
            const id = '123e4567-e89b-12d3-a456-426614174000';
            vi.mocked(api.getSession).mockResolvedValueOnce(
                sessionDetail([], { id }),
            );

            await expect(state().openSession(id)).resolves.toBe('ok');

            expect(api.getSession).toHaveBeenCalledWith(id);
        });
    });

    describe('読み込みの失敗', () => {
        async function failToOpen() {
            vi.mocked(api.getSession).mockRejectedValueOnce(
                new TypeError('Failed to fetch'),
            );
            await expect(state().openSession('s1')).resolves.toBe('error');
        }

        it('履歴が見えないセッションへは送らない', async () => {
            await failToOpen();

            expect(selectHasLoadFailed(state())).toBe(true);
            expect(selectIsSendDisabled(state())).toBe(true);
            await expect(state().sendMessage('こんにちは')).resolves.toBe(
                'not-sent',
            );
            expect(api.streamMessage).not.toHaveBeenCalled();
            expect(state().messages).toEqual([]);
        });

        it('読み込み中は失敗の扱いにしない', () => {
            vi.mocked(api.getSession).mockImplementationOnce(
                () => new Promise(() => {}),
            );

            void state().openSession('s1');

            expect(selectHasLoadFailed(state())).toBe(false);
        });

        it('新規チャットと読み込み済みのセッションは失敗の扱いにしない', async () => {
            expect(selectHasLoadFailed(state())).toBe(false);

            await openSession();

            expect(selectHasLoadFailed(state())).toBe(false);
        });

        it('読み直せる。リマウントはさせない', async () => {
            await failToOpen();
            const key = state().threadKey;
            vi.mocked(api.getSession).mockResolvedValueOnce(
                sessionDetail([userMessage()]),
            );

            await expect(state().retryOpenSession()).resolves.toBe('ok');

            expect(selectHasLoadFailed(state())).toBe(false);
            expect(state().error).toBeNull();
            expect(state().messages).toHaveLength(1);
            expect(state().activeSession?.id).toBe('s1');
            expect(state().threadKey).toBe(key);
        });

        it('読み直して見つからなければ not-found を返す', async () => {
            await failToOpen();
            vi.mocked(api.getSession).mockRejectedValueOnce(
                httpError(null, 404),
            );

            await expect(state().retryOpenSession()).resolves.toBe('not-found');

            expect(state().activeSessionId).toBeNull();
        });

        it('失敗していなければ読み直さない', async () => {
            await expect(state().retryOpenSession()).resolves.toBe('stale');

            await openSession();
            await expect(state().retryOpenSession()).resolves.toBe('stale');

            expect(api.getSession).toHaveBeenCalledTimes(1);
        });
    });

    describe('音声の取得と切り替え', () => {
        const withAudio = [
            userMessage(),
            assistantMessage({ audio_url: '/a/2/', audio_size_bytes: 3 }),
        ];

        it('取得の途中で離れて戻っても、取り直して表示できる', async () => {
            await openSession('s1', withAudio);
            const first = deferred<Blob>();
            vi.mocked(api.fetchAudioBlob).mockReturnValueOnce(first.promise);
            const firstUrl = state().ensureAudioObjectUrl(2);
            await openSession('s2');
            await openSession('s1', withAudio);
            vi.mocked(api.fetchAudioBlob).mockResolvedValueOnce(
                new Blob(['abc']),
            );

            const secondUrl = state().ensureAudioObjectUrl(2);
            await expect(secondUrl).resolves.toBe('blob:3');
            first.resolve(new Blob(['abc']));

            await expect(firstUrl).resolves.toBeNull();
            expect(api.fetchAudioBlob).toHaveBeenCalledTimes(2);
            expect(state().audioObjectUrls.get(2)).toBe('blob:3');
        });

        it('古い取得が終わっても新しい取得の記録を消さない', async () => {
            await openSession('s1', withAudio);
            const first = deferred<Blob>();
            vi.mocked(api.fetchAudioBlob).mockReturnValueOnce(first.promise);
            const firstUrl = state().ensureAudioObjectUrl(2);
            await openSession('s2');
            await openSession('s1', withAudio);
            const second = deferred<Blob>();
            vi.mocked(api.fetchAudioBlob).mockReturnValueOnce(second.promise);
            const secondUrl = state().ensureAudioObjectUrl(2);

            first.resolve(new Blob(['abc']));
            await firstUrl;
            const again = state().ensureAudioObjectUrl(2);
            second.resolve(new Blob(['abc']));

            await expect(again).resolves.toBe('blob:3');
            await expect(secondUrl).resolves.toBe('blob:3');
            expect(api.fetchAudioBlob).toHaveBeenCalledTimes(2);
        });
    });

    describe('同期の上限', () => {
        it('GET に残り時間を渡して再試行させず、固まっても 10 秒で諦める', async () => {
            await openSession('s1', [userMessage(), assistantMessage()]);
            nextStreamMessage(controlledStream());
            void state().sendMessage('こんにちは');
            await flush();
            // ky の timeout と同じく、渡された時間で失敗する GET
            vi.mocked(api.getSession).mockImplementation(
                (_id, options) =>
                    new Promise((_resolve, reject) => {
                        setTimeout(
                            () => reject(new Error('timeout')),
                            options?.timeout,
                        );
                    }),
            );

            state().cancelRun();
            await flush();
            expect(state().isSyncing).toBe(true);
            expect(api.getSession).toHaveBeenLastCalledWith(
                's1',
                expect.objectContaining({ retry: 0 }),
            );
            await vi.advanceTimersByTimeAsync(10_000);

            expect(state().isSyncing).toBe(false);
            expect(state().error).not.toBeNull();
            expect(selectIsSendDisabled(state())).toBe(false);
        });

        it('期限を過ぎてから新しい GET を始めない', async () => {
            await openSession('s1', [userMessage(), assistantMessage()]);
            nextStreamMessage(controlledStream());
            void state().sendMessage('こんにちは');
            await flush();
            vi.mocked(api.getSession).mockResolvedValue(
                sessionDetail([userMessage(), assistantMessage()]),
            );

            state().cancelRun();
            await vi.advanceTimersByTimeAsync(10_000);

            const timeouts = vi
                .mocked(api.getSession)
                .mock.calls.slice(1)
                .map(([, options]) => options?.timeout ?? 0);
            expect(state().isSyncing).toBe(false);
            expect(Math.min(...timeouts)).toBeGreaterThan(0);
        });
    });

    describe('編集の失敗と音声の待ち', () => {
        async function savedTurnWaitingForAudio() {
            await openSession('s1', [], { tts_enabled: true });
            const first = controlledStream();
            nextStreamMessage(first);
            void state().sendMessage('こんにちは');
            first.push(savedTurn);
            await flush();
            expect(state().messages[1].audioState).toBe('pending');
            return first;
        }

        it('待っていたターンが編集の間に終わっていたら合成中を解き、音声を読み直す', async () => {
            const first = await savedTurnWaitingForAudio();
            const edit = controlledStream();
            nextStreamEdit(edit);
            const result = state().editMessage(
                state().messages[0].localId,
                '直した',
            );
            await flush();
            first.push(
                {
                    type: 'audio',
                    message_id: 11,
                    audio_url: '/a/11/',
                    audio_format: 'wav',
                    audio_size_bytes: 9,
                },
                doneEvent,
            );
            first.end();
            await flush();
            vi.mocked(api.getSession).mockResolvedValueOnce(
                sessionDetail(
                    [
                        savedTurn.user,
                        {
                            ...savedTurn.assistant,
                            audio_url: '/a/11/',
                            audio_format: 'wav',
                            audio_size_bytes: 9,
                        },
                    ],
                    { tts_enabled: true },
                ),
            );

            edit.push({ type: 'error', status: 502, error: '失敗' });
            await expect(result).resolves.toBe('not-sent');
            await flush();

            expect(state().messages[1]).toMatchObject({
                id: 11,
                audioState: 'idle',
                audio_url: '/a/11/',
            });
            expect(state().error).toBe('失敗');
        });

        it('待っていたターンがまだ続いていれば合成中を保ち、届いたら反映する', async () => {
            const first = await savedTurnWaitingForAudio();
            const edit = controlledStream();
            nextStreamEdit(edit);
            const result = state().editMessage(
                state().messages[0].localId,
                '直した',
            );
            await flush();

            edit.push({ type: 'error', status: 502, error: '失敗' });
            await expect(result).resolves.toBe('not-sent');

            expect(state().messages[1].audioState).toBe('pending');

            first.push({
                type: 'audio',
                message_id: 11,
                audio_url: '/a/11/',
                audio_format: 'wav',
                audio_size_bytes: 9,
            });
            await flush();

            expect(state().messages[1]).toMatchObject({
                audioState: 'idle',
                audio_url: '/a/11/',
            });
        });
    });

    describe('生成中にチャットを離れたとき', () => {
        const prior = [userMessage(), assistantMessage()];
        const saved = [
            ...prior,
            userMessage({ id: 3, sequence: 2, content: '途中の発話' }),
            assistantMessage({ id: 4, sequence: 3, content: '途中まで' }),
        ];

        /** サーバーの状態。テストの途中で書き換えて、保存が済んだことにする。 */
        let serverSessions: Map<string, ChatSessionDetail>;

        async function leaveWhileStreaming() {
            serverSessions = new Map([
                ['s1', sessionDetail(prior)],
                ['s2', sessionDetail([], { id: 's2' })],
            ]);
            vi.mocked(api.getSession).mockImplementation(async (id) => {
                const session = serverSessions.get(id);
                if (!session) throw httpError(null, 404);
                return session;
            });
            vi.mocked(api.listSessions).mockResolvedValueOnce({
                count: 2,
                next: null,
                previous: null,
                results: [
                    sessionItem({ message_count: 2 }),
                    sessionItem({ id: 's2', title: '別' }),
                ],
            });
            await state().loadSessions();
            await state().openSession('s1');
            const stream = controlledStream();
            nextStreamMessage(stream);
            void state().sendMessage('途中の発話');
            stream.push({ type: 'delta', text: '途中' });
            await flush();
            await state().openSession('s2');
            await flush();
        }

        it('別のチャットを見ている間に保存されたら一覧の件数を更新する', async () => {
            await leaveWhileStreaming();
            serverSessions.set('s1', sessionDetail(saved));

            await vi.advanceTimersByTimeAsync(500);

            expect(state().sessions[0].message_count).toBe(4);
            expect(state().activeSessionId).toBe('s2');
            expect(state().messages).toEqual([]);
            expect(state().isSyncing).toBe(false);
        });

        it('保存の前に戻ってきても、保存されたら表示に反映する', async () => {
            await leaveWhileStreaming();
            await state().openSession('s1');
            expect(state().messages).toHaveLength(2);
            serverSessions.set('s1', sessionDetail(saved));

            await vi.advanceTimersByTimeAsync(500);

            expect(state().messages.map((m) => m.content)).toEqual([
                'おはよう',
                'おはようございます',
                '途中の発話',
                '途中まで',
            ]);
        });

        it('戻って次を生成している間は表示を巻き戻さない', async () => {
            await leaveWhileStreaming();
            await state().openSession('s1');
            nextStreamMessage(controlledStream());
            void state().sendMessage('次の発話');
            serverSessions.set('s1', sessionDetail(saved));

            await vi.advanceTimersByTimeAsync(500);

            expect(state().isRunning).toBe(true);
            expect(state().messages.at(-1)?.content).toBe('次の発話');
            expect(state().sessions[0].message_count).toBe(4);
        });

        it('保存が確認できなければ 10 秒で確認をやめる', async () => {
            await leaveWhileStreaming();

            await vi.advanceTimersByTimeAsync(10_000);
            const calls = vi.mocked(api.getSession).mock.calls.length;
            await vi.advanceTimersByTimeAsync(10_000);

            expect(vi.mocked(api.getSession).mock.calls.length).toBe(calls);
            expect(state().error).toBeNull();
        });

        it('セッションが消えていれば確認をやめる', async () => {
            await leaveWhileStreaming();
            serverSessions.delete('s1');
            await vi.advanceTimersByTimeAsync(500);
            const calls = vi.mocked(api.getSession).mock.calls.length;

            await vi.advanceTimersByTimeAsync(10_000);

            expect(vi.mocked(api.getSession).mock.calls.length).toBe(calls);
            expect(state().activeSessionId).toBe('s2');
            expect(state().error).toBeNull();
        });

        it('確認の途中でチャットの画面を離れたらやめる', async () => {
            await leaveWhileStreaming();
            state().reset();
            serverSessions.set('s1', sessionDetail(saved));
            vi.mocked(api.getSession).mockClear();

            await vi.advanceTimersByTimeAsync(10_000);

            expect(api.getSession).not.toHaveBeenCalled();
            expect(state().sessions).toEqual([]);
        });

        it('チャットの画面を離れたら確認しない', async () => {
            await openSession('s1', prior);
            nextStreamMessage(controlledStream());
            void state().sendMessage('途中の発話');
            await flush();
            vi.mocked(api.getSession).mockClear();

            state().reset();
            await vi.advanceTimersByTimeAsync(10_000);

            expect(api.getSession).not.toHaveBeenCalled();
        });

        it('生成中のセッションを消したら確認しない', async () => {
            await openSession('s1', prior);
            nextStreamMessage(controlledStream());
            void state().sendMessage('途中の発話');
            await flush();
            vi.mocked(api.getSession).mockClear();

            await state().removeSession('s1');
            await vi.advanceTimersByTimeAsync(10_000);

            expect(api.getSession).not.toHaveBeenCalled();
        });
    });

    describe('遅延作成中の停止', () => {
        it('作成の応答を待たずに not-sent を返し、作られたら消す', async () => {
            vi.mocked(api.fetchSettings).mockResolvedValueOnce([voiced]);
            await state().loadSettings();
            const created = deferred<ChatSessionDetail>();
            vi.mocked(api.createSession).mockReturnValueOnce(created.promise);

            const result = state().sendMessage('こんにちは');
            state().cancelRun();

            await expect(result).resolves.toBe('not-sent');
            expect(api.deleteSession).not.toHaveBeenCalled();

            created.resolve(sessionDetail([], { id: 'new' }));
            await flush();

            expect(api.deleteSession).toHaveBeenCalledWith('new');
            expect(api.streamMessage).not.toHaveBeenCalled();
            expect(state().activeSessionId).toBeNull();
            expect(state().sessions).toEqual([]);
        });

        it('作成が失敗しても文言を出さない', async () => {
            vi.mocked(api.fetchSettings).mockResolvedValueOnce([voiced]);
            await state().loadSettings();
            const created = deferred<ChatSessionDetail>();
            vi.mocked(api.createSession).mockReturnValueOnce(created.promise);

            const result = state().sendMessage('こんにちは');
            state().cancelRun();
            await result;
            created.reject(httpError({ error: '作成できません' }, 503));
            await flush();

            expect(state().error).toBeNull();
        });
    });

    describe('古い読み直しの応答', () => {
        it('読み直しの間に次のターンが保存されたら、古い応答で行を消さない', async () => {
            await openSession();
            const first = controlledStream();
            nextStreamMessage(first);
            void state().sendMessage('こんにちは');
            first.push(savedTurn);
            await flush();
            const second = controlledStream();
            nextStreamMessage(second);
            void state().sendMessage('次の発話');
            await flush();
            const get = deferred<ChatSessionDetail>();
            vi.mocked(api.getSession).mockReturnValueOnce(get.promise);
            first.fail(new TypeError('network error'));
            await flush();
            second.push({
                type: 'message',
                user: userMessage({ id: 12, sequence: 2, content: '次の発話' }),
                assistant: assistantMessage({
                    id: 13,
                    sequence: 3,
                    content: '次の応答',
                }),
            });
            await flush();
            expect(state().messages.map((m) => m.id)).toEqual([10, 11, 12, 13]);

            get.resolve(sessionDetail([savedTurn.user, savedTurn.assistant]));
            await flush();

            expect(state().messages.map((m) => m.id)).toEqual([10, 11, 12, 13]);
        });
    });

    describe('行のオブジェクトの維持', () => {
        // 編集欄を開いている間に行が差し替わると、失敗しても編集欄を開き直せない
        it('音声の一括削除で音声のない行を差し替えない', async () => {
            await openSession('s1', [
                userMessage(),
                assistantMessage({ audio_url: '/a/2/', audio_size_bytes: 3 }),
            ]);
            const [user] = state().messages;
            vi.mocked(api.bulkDeleteAudio).mockResolvedValueOnce(undefined);

            await state().deleteAllAudio();

            expect(state().messages[0]).toBe(user);
            expect(state().messages[1].audio_url).toBeNull();
        });
    });

    describe('セッションの削除の結果', () => {
        it('表示中のセッションを消したら active を返す', async () => {
            await openSession();

            await expect(state().removeSession('s1')).resolves.toBe('active');
        });

        it('別のセッションを消したら other を返す', async () => {
            await openSession();

            await expect(state().removeSession('s2')).resolves.toBe('other');
        });

        it('応答を待つ間に別のチャットへ移っていたら other を返す', async () => {
            await openSession();
            const removal = deferred<void>();
            vi.mocked(api.deleteSession).mockReturnValueOnce(removal.promise);

            const result = state().removeSession('s1');
            await openSession('s2');
            removal.resolve();

            await expect(result).resolves.toBe('other');
            expect(state().activeSessionId).toBe('s2');
        });

        it('消せなければ failed を返す', async () => {
            await openSession();
            vi.mocked(api.deleteSession).mockRejectedValueOnce(new Error('x'));

            await expect(state().removeSession('s1')).resolves.toBe('failed');

            expect(state().activeSessionId).toBe('s1');
        });
    });

    describe('別のタブで消されたセッション', () => {
        const history = [userMessage(), assistantMessage()];

        it('送信が 404 なら確かめて手放し、理由を出す', async () => {
            await openSession('s1', history);
            vi.mocked(api.streamMessage).mockImplementationOnce(
                // eslint-disable-next-line require-yield
                async function* () {
                    throw httpError(null, 404);
                },
            );
            vi.mocked(api.getSession).mockRejectedValueOnce(
                httpError(null, 404),
            );
            const onSessionAbandoned = vi.fn();

            await expect(
                state().sendMessage('こんにちは', { onSessionAbandoned }),
            ).resolves.toBe('not-sent');
            await flush();

            expect(onSessionAbandoned).toHaveBeenCalledTimes(1);
            expect(state().activeSessionId).toBeNull();
            expect(state().messages).toEqual([]);
            expect(state().error).toBe('このチャットは削除されています');
        });

        it('SSE の error が 404 なら確かめて手放す', async () => {
            await openSession('s1', history);
            const stream = controlledStream();
            nextStreamMessage(stream);
            vi.mocked(api.getSession).mockRejectedValueOnce(
                httpError(null, 404),
            );
            const onSessionAbandoned = vi.fn();
            const result = state().sendMessage('こんにちは', {
                onSessionAbandoned,
            });

            stream.push({
                type: 'error',
                status: 404,
                error: 'セッションが削除されました',
            });
            await expect(result).resolves.toBe('not-sent');
            await flush();

            expect(onSessionAbandoned).toHaveBeenCalledTimes(1);
            expect(state().activeSessionId).toBeNull();
        });

        it('編集の 404 でも手放す', async () => {
            await openSession('s1', history);
            vi.mocked(api.streamEdit).mockImplementationOnce(
                // eslint-disable-next-line require-yield
                async function* () {
                    throw httpError(null, 404);
                },
            );
            vi.mocked(api.getSession).mockRejectedValueOnce(
                httpError(null, 404),
            );
            const onSessionAbandoned = vi.fn();

            await state().editMessage(state().messages[0].localId, '直した', {
                onSessionAbandoned,
            });
            await flush();

            expect(onSessionAbandoned).toHaveBeenCalledTimes(1);
            expect(state().activeSessionId).toBeNull();
        });

        it('再生成の 404 でも手放す', async () => {
            await openSession('s1', history);
            vi.mocked(api.streamEdit).mockImplementationOnce(
                // eslint-disable-next-line require-yield
                async function* () {
                    throw httpError(null, 404);
                },
            );
            vi.mocked(api.getSession).mockRejectedValueOnce(
                httpError(null, 404),
            );
            const onSessionAbandoned = vi.fn();

            await state().regenerate(state().messages[0].localId, {
                onSessionAbandoned,
            });
            await flush();

            expect(onSessionAbandoned).toHaveBeenCalledTimes(1);
        });

        it('編集対象が消えた 404 ならセッションは残す', async () => {
            await openSession('s1', history);
            vi.mocked(api.streamEdit).mockImplementationOnce(
                // eslint-disable-next-line require-yield
                async function* () {
                    throw httpError(null, 404);
                },
            );
            vi.mocked(api.getSession).mockResolvedValueOnce(
                sessionDetail(history),
            );
            const onSessionAbandoned = vi.fn();

            await expect(
                state().editMessage(state().messages[0].localId, '直した', {
                    onSessionAbandoned,
                }),
            ).resolves.toBe('not-sent');
            await flush();

            // 開いたときと、消えていないかの確認の 2 回
            expect(api.getSession).toHaveBeenCalledTimes(2);
            expect(onSessionAbandoned).not.toHaveBeenCalled();
            expect(state().activeSessionId).toBe('s1');
            expect(state().messages.map((m) => m.content)).toEqual(
                history.map((m) => m.content),
            );
            expect(state().error).toBe('応答の生成に失敗しました');
        });

        it('確かめる間に別のチャットへ移っていたら何もしない', async () => {
            await openSession('s1', history);
            vi.mocked(api.streamMessage).mockImplementationOnce(
                // eslint-disable-next-line require-yield
                async function* () {
                    throw httpError(null, 404);
                },
            );
            const check = deferred<ChatSessionDetail>();
            vi.mocked(api.getSession).mockReturnValueOnce(check.promise);
            const onSessionAbandoned = vi.fn();
            await state().sendMessage('こんにちは', { onSessionAbandoned });
            await openSession('s2');

            check.reject(httpError(null, 404));
            await flush();

            expect(onSessionAbandoned).not.toHaveBeenCalled();
            expect(state().activeSessionId).toBe('s2');
        });

        it('同期中に消えていたら理由を出す', async () => {
            await openSession('s1', history);
            nextStreamMessage(controlledStream());
            const result = state().sendMessage('こんにちは');
            await flush();
            vi.mocked(api.getSession).mockRejectedValueOnce(
                httpError(null, 404),
            );

            state().cancelRun();
            await flush();

            await expect(result).resolves.toBe('not-sent');
            expect(state().error).toBe('このチャットは削除されています');
        });
    });

    describe('契約から外れた応答', () => {
        it('保存の通知が壊れていても生成中のまま止まらない', async () => {
            await openSession();
            const stream = controlledStream();
            nextStreamMessage(stream);
            const result = state().sendMessage('こんにちは');
            vi.mocked(api.getSession).mockResolvedValueOnce(
                sessionDetail([savedTurn.user, savedTurn.assistant]),
            );

            stream.push({
                type: 'message',
                user: savedTurn.user,
                assistant: null as never,
            });
            await flush();

            await expect(result).resolves.toBe('sent');
            expect(state().isRunning).toBe(false);
        });
    });
});
