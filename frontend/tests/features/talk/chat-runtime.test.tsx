import {
    type AssistantRuntime,
    AssistantRuntimeProvider,
} from '@assistant-ui/react';
import { act, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useChatRuntime } from '@/features/talk/useChatRuntime';
import * as api from '@/lib/api/talk';
import { useChatStore } from '@/stores/chat-store';
import type { ChatSessionDetail, ChatSessionMessage } from '@/types/talk';
import {
    controlledStream,
    type ControlledStream,
} from '../../helpers/chat-stream';

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

const reply = serverMessage({
    id: 2,
    sequence: 1,
    role: 'assistant',
    content: 'おはようございます',
});

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

const store = () => useChatStore.getState();

function Host({ onRuntime }: { onRuntime: (r: AssistantRuntime) => void }) {
    const runtime = useChatRuntime();
    onRuntime(runtime);
    const { pathname } = useLocation();
    return (
        <AssistantRuntimeProvider runtime={runtime}>
            <output data-testid="pathname">{pathname}</output>
        </AssistantRuntimeProvider>
    );
}

function setup(path = '/talk/s1') {
    const probe: { runtime?: AssistantRuntime } = {};
    render(
        <MemoryRouter initialEntries={[path]}>
            <Host
                onRuntime={(runtime) => {
                    probe.runtime = runtime;
                }}
            />
        </MemoryRouter>,
    );
    return {
        runtime: () => probe.runtime as AssistantRuntime,
    };
}

const threadState = (runtime: AssistantRuntime) => runtime.thread.getState();

async function openSession(messages: readonly ChatSessionMessage[]) {
    vi.mocked(api.getSession).mockResolvedValueOnce(detail(messages));
    await act(async () => {
        await store().openSession('s1');
    });
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

async function send(runtime: AssistantRuntime, text: string) {
    await act(async () => {
        runtime.thread.composer.setText(text);
        await runtime.thread.composer.send();
    });
}

async function push(
    stream: ControlledStream,
    ...events: Parameters<ControlledStream['push']>
) {
    await act(async () => {
        stream.push(...events);
        await new Promise((resolve) => setTimeout(resolve, 0));
    });
}

describe('useChatRuntime', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(api.deleteSession).mockResolvedValue(undefined);
    });

    afterEach(() => {
        act(() => store().reset());
    });

    describe('表示の変換', () => {
        it('ストアの行を id、役割、本文、metadata.custom へ変換する', async () => {
            const { runtime } = setup();

            await openSession([
                serverMessage(),
                {
                    ...reply,
                    audio_url: '/a/2/',
                    audio_format: 'wav',
                    audio_size_bytes: 64,
                },
            ]);

            const [user, assistant] = threadState(runtime()).messages;
            expect(user).toMatchObject({
                id: 'srv-1',
                role: 'user',
                content: [{ type: 'text', text: 'おはよう' }],
            });
            expect(assistant).toMatchObject({
                id: 'srv-2',
                role: 'assistant',
                status: { type: 'complete', reason: 'stop' },
                metadata: {
                    custom: {
                        serverId: 2,
                        audio_url: '/a/2/',
                        audio_format: 'wav',
                        audio_size_bytes: 64,
                        audioState: 'idle',
                        audioError: null,
                    },
                },
            });
            expect(assistant.createdAt).toEqual(new Date(NOW));
        });

        it('読み込み中を runtime に伝える', () => {
            const { runtime } = setup();
            vi.mocked(api.getSession).mockImplementationOnce(
                () => new Promise(() => {}),
            );

            act(() => {
                void store().openSession('s1');
            });

            expect(threadState(runtime()).isLoading).toBe(true);
        });

        it('送信できないときは送信を止める', async () => {
            const { runtime } = setup();
            const fifty = Array.from({ length: 50 }, (_, i) =>
                serverMessage({
                    id: i + 1,
                    sequence: i,
                    role: i % 2 === 0 ? 'user' : 'assistant',
                }),
            );

            await openSession(fifty);

            expect(threadState(runtime()).isSendDisabled).toBe(true);
            act(() => runtime().thread.composer.setText('次'));
            expect(runtime().thread.composer.getState().canSend).toBe(false);
        });
    });

    describe('送信', () => {
        it('応答が届くまでは上流の楽観的な assistant を出し、最初の差分で本物に替える', async () => {
            const { runtime } = setup();
            await openSession([]);
            const stream = controlledStream();
            nextStreamMessage(stream);

            await send(runtime(), 'こんにちは');

            const pending = threadState(runtime()).messages;
            expect(pending).toHaveLength(2);
            expect(pending[0]).toMatchObject({ role: 'user' });
            expect(pending[1]).toMatchObject({
                role: 'assistant',
                content: [],
                status: { type: 'running' },
                metadata: { isOptimistic: true },
            });
            expect(store().messages).toHaveLength(1);

            await push(stream, { type: 'delta', text: 'こん' });

            const streaming = threadState(runtime()).messages;
            expect(streaming).toHaveLength(2);
            expect(streaming[1]).toMatchObject({
                content: [{ type: 'text', text: 'こん' }],
                status: { type: 'running' },
            });
            expect(streaming[1].metadata.isOptimistic).toBeFalsy();
        });

        it('保存の通知が来ても id を変えない（行をリマウントさせない）', async () => {
            const { runtime } = setup();
            await openSession([]);
            const stream = controlledStream();
            nextStreamMessage(stream);
            await send(runtime(), 'こんにちは');
            await push(stream, { type: 'delta', text: '応答' });
            const before = threadState(runtime()).messages.map((m) => m.id);

            await push(stream, {
                type: 'message',
                user: serverMessage({ id: 10, content: 'こんにちは' }),
                assistant: { ...reply, id: 11, content: '応答' },
            });

            const after = threadState(runtime());
            expect(after.isRunning).toBe(false);
            expect(after.messages.map((m) => m.id)).toEqual(before);
            expect(after.messages[1].metadata.custom).toMatchObject({
                serverId: 11,
            });
            expect(after.messages[1].status).toEqual({
                type: 'complete',
                reason: 'stop',
            });
        });

        it('失敗したら発話を取り消して入力文を入力欄へ戻す', async () => {
            const { runtime } = setup();
            await openSession([serverMessage(), reply]);
            const stream = controlledStream();
            nextStreamMessage(stream);
            await send(runtime(), 'こんにちは');
            expect(runtime().thread.composer.getState().text).toBe('');

            await push(stream, {
                type: 'error',
                status: 502,
                error: 'LLM に接続できません',
            });

            await waitFor(() => {
                expect(runtime().thread.composer.getState().text).toBe(
                    'こんにちは',
                );
            });
            expect(threadState(runtime()).messages).toHaveLength(2);
            expect(threadState(runtime()).isRunning).toBe(false);
            expect(store().error).toBe('LLM に接続できません');
        });

        it('生成中に別の送信が走ってしまっても入力文を失わない', async () => {
            const { runtime } = setup();
            await openSession([]);
            nextStreamMessage(controlledStream());
            await send(runtime(), '1 件目');

            await send(runtime(), '2 件目');

            await waitFor(() => {
                expect(runtime().thread.composer.getState().text).toBe(
                    '2 件目',
                );
            });
            expect(store().messages.map((m) => m.content)).toEqual(['1 件目']);
        });
    });

    describe('新規チャット', () => {
        async function ready() {
            vi.mocked(api.fetchConfigs).mockResolvedValueOnce([
                {
                    name: 'friendly',
                    display_name: 'フレンドリー',
                    tts_enabled: false,
                },
            ]);
            await act(async () => {
                await store().loadConfigs();
            });
        }

        it('作成したセッションの URL へ移る', async () => {
            const { runtime } = setup('/talk');
            await ready();
            vi.mocked(api.createSession).mockResolvedValueOnce(
                detail([], { id: 'new' }),
            );
            nextStreamMessage(controlledStream());

            await send(runtime(), 'こんにちは');

            await waitFor(() => {
                expect(screen.getByTestId('pathname')).toHaveTextContent(
                    '/talk/new',
                );
            });
            expect(threadState(runtime()).messages[0]).toMatchObject({
                role: 'user',
            });
        });

        it('応答に失敗したら /talk へ戻して入力文を入力欄へ戻す', async () => {
            const { runtime } = setup('/talk');
            await ready();
            vi.mocked(api.createSession).mockResolvedValueOnce(
                detail([], { id: 'new' }),
            );
            const stream = controlledStream();
            nextStreamMessage(stream);
            await send(runtime(), 'こんにちは');
            await waitFor(() => {
                expect(screen.getByTestId('pathname')).toHaveTextContent(
                    '/talk/new',
                );
            });

            await push(stream, { type: 'error', status: 502, error: '失敗' });

            await waitFor(() => {
                expect(screen.getByTestId('pathname').textContent).toBe(
                    '/talk',
                );
                expect(runtime().thread.composer.getState().text).toBe(
                    'こんにちは',
                );
            });
            expect(api.deleteSession).toHaveBeenCalledWith('new');
            expect(threadState(runtime()).messages).toEqual([]);
        });
    });

    describe('停止', () => {
        it('発話を残し、入力欄は変えない', async () => {
            const { runtime } = setup();
            await openSession([]);
            const stream = controlledStream();
            nextStreamMessage(stream);
            await send(runtime(), 'こんにちは');
            await push(stream, { type: 'delta', text: '途中' });
            vi.mocked(api.getSession).mockImplementation(
                () => new Promise(() => {}),
            );

            act(() => runtime().thread.cancelRun());

            await waitFor(() => {
                expect(threadState(runtime()).isRunning).toBe(false);
            });
            const { messages } = threadState(runtime());
            expect(messages.map((m) => m.role)).toEqual(['user', 'assistant']);
            expect(messages[0].content).toEqual([
                { type: 'text', text: 'こんにちは' },
            ]);
            expect(messages[1].status).toEqual({
                type: 'incomplete',
                reason: 'cancelled',
            });
            expect(runtime().thread.composer.getState().text).toBe('');
            expect(store().isSyncing).toBe(true);
            expect(threadState(runtime()).isSendDisabled).toBe(true);
        });

        it('応答の前に停止しても発話を残し、空の assistant を残さない', async () => {
            const { runtime } = setup();
            await openSession([]);
            nextStreamMessage(controlledStream());
            await send(runtime(), 'こんにちは');
            vi.mocked(api.getSession).mockImplementation(
                () => new Promise(() => {}),
            );

            act(() => runtime().thread.cancelRun());

            await waitFor(() => {
                expect(
                    threadState(runtime()).messages.map((m) => m.role),
                ).toEqual(['user']);
            });
            expect(runtime().thread.composer.getState().text).toBe('');
        });
    });

    describe('編集', () => {
        const history = [
            serverMessage({ id: 1, sequence: 0, content: '元の発話' }),
            { ...reply, id: 2, sequence: 1 },
        ];

        async function beginEdit(runtime: AssistantRuntime, text: string) {
            const message = runtime.thread.getMessageById('srv-1');
            act(() => message.composer.beginEdit());
            act(() => message.composer.setText(text));
            return message;
        }

        it('編集を送ると対象を差し替えて再送し、id を変えない', async () => {
            const { runtime } = setup();
            await openSession(history);
            const stream = controlledStream();
            nextStreamEdit(stream);
            const message = await beginEdit(runtime(), '直した');

            await act(async () => {
                await message.composer.send();
            });

            expect(api.streamEdit).toHaveBeenCalledWith(
                's1',
                1,
                '直した',
                expect.anything(),
            );
            const { messages, isRunning } = threadState(runtime());
            expect(isRunning).toBe(true);
            expect(messages[0]).toMatchObject({
                id: 'srv-1',
                content: [{ type: 'text', text: '直した' }],
            });
            expect(message.composer.getState().isEditing).toBe(false);

            await push(stream, {
                type: 'message',
                user: serverMessage({ id: 5, content: '直した' }),
                assistant: { ...reply, id: 6, content: '新しい応答' },
            });

            const after = threadState(runtime()).messages;
            expect(after.map((m) => m.role)).toEqual(['user', 'assistant']);
            expect(after[0].id).toBe('srv-1');
            expect(after[0].metadata.custom).toMatchObject({ serverId: 5 });
            expect(after[1].content).toEqual([
                { type: 'text', text: '新しい応答' },
            ]);
        });

        it('失敗したら元の履歴へ戻し、編集を入力文ごと開き直す', async () => {
            const { runtime } = setup();
            await openSession(history);
            const stream = controlledStream();
            nextStreamEdit(stream);
            const message = await beginEdit(runtime(), '直した');
            await act(async () => {
                await message.composer.send();
            });

            await push(stream, { type: 'error', status: 502, error: '失敗' });

            await waitFor(() => {
                const state = runtime().thread.getMessageById('srv-1').composer;
                expect(state.getState().isEditing).toBe(true);
                expect(state.getState().text).toBe('直した');
            });
            const { messages } = threadState(runtime());
            expect(messages.map((m) => m.id)).toEqual(['srv-1', 'srv-2']);
            expect(messages[0].content).toEqual([
                { type: 'text', text: '元の発話' },
            ]);
            expect(store().error).toBe('失敗');
        });

        it('HTTP エラーでも編集を開き直す', async () => {
            const { runtime } = setup();
            await openSession(history);
            vi.mocked(api.streamEdit).mockImplementationOnce(
                // eslint-disable-next-line require-yield
                async function* () {
                    throw new TypeError('Failed to fetch');
                },
            );
            const message = await beginEdit(runtime(), '直した');

            await act(async () => {
                await message.composer.send();
            });

            await waitFor(() => {
                const state = runtime().thread.getMessageById('srv-1').composer;
                expect(state.getState().isEditing).toBe(true);
                expect(state.getState().text).toBe('直した');
            });
        });
    });

    describe('再生成', () => {
        const history = [serverMessage(), reply];

        it('直前の発話を同じ本文で編集 API に送る', async () => {
            const { runtime } = setup();
            await openSession(history);
            nextStreamEdit(controlledStream());

            await act(async () => {
                runtime().thread.getMessageById('srv-2').reload();
            });

            expect(api.streamEdit).toHaveBeenCalledWith(
                's1',
                1,
                'おはよう',
                expect.anything(),
            );
            expect(threadState(runtime()).isRunning).toBe(true);
        });

        it('失敗したらバナーだけ出して元の表示へ戻す', async () => {
            const { runtime } = setup();
            await openSession(history);
            const stream = controlledStream();
            nextStreamEdit(stream);
            await act(async () => {
                runtime().thread.getMessageById('srv-2').reload();
            });

            await push(stream, {
                type: 'error',
                status: 504,
                error: '時間切れ',
            });

            await waitFor(() => {
                expect(threadState(runtime()).isRunning).toBe(false);
            });
            expect(threadState(runtime()).messages.map((m) => m.id)).toEqual([
                'srv-1',
                'srv-2',
            ]);
            expect(store().error).toBe('時間切れ');
            expect(
                runtime().thread.getMessageById('srv-1').composer.getState()
                    .isEditing,
            ).toBe(false);
            expect(runtime().thread.composer.getState().text).toBe('');
        });
    });
});
