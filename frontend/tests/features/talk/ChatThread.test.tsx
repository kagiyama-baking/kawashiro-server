import { AssistantRuntimeProvider } from '@assistant-ui/react';
import {
    act,
    fireEvent,
    render,
    screen,
    waitFor,
    within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatThread } from '@/features/talk/ChatThread';
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

function userMessage(
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
    return userMessage({
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

const friendly = {
    name: 'friendly',
    display_name: 'フレンドリー',
    tts_enabled: false,
};
const voiced = { name: 'voiced', display_name: '音声あり', tts_enabled: true };

const store = () => useChatStore.getState();

function Host() {
    const runtime = useChatRuntime();
    return (
        <AssistantRuntimeProvider runtime={runtime}>
            <ChatThread />
        </AssistantRuntimeProvider>
    );
}

function renderThread() {
    render(
        <MemoryRouter>
            <Host />
        </MemoryRouter>,
    );
    return { user: userEvent.setup() };
}

async function loadConfigs(configs = [friendly]) {
    vi.mocked(api.fetchConfigs).mockResolvedValueOnce(configs);
    await act(async () => {
        await store().loadConfigs();
    });
}

async function openSession(
    messages: readonly ChatSessionMessage[] = [
        userMessage(),
        assistantMessage(),
    ],
    overrides: Partial<ChatSessionDetail> = {},
) {
    vi.mocked(api.getSession).mockResolvedValueOnce(
        detail(messages, overrides),
    );
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

async function push(
    stream: ControlledStream,
    ...events: Parameters<ControlledStream['push']>
) {
    await act(async () => {
        stream.push(...events);
        await new Promise((resolve) => setTimeout(resolve, 0));
    });
}

const composerInput = () =>
    screen.getByRole('textbox', { name: 'メッセージ' }) as HTMLTextAreaElement;

function typeText(input: HTMLTextAreaElement, text: string) {
    fireEvent.change(input, { target: { value: text } });
}

async function answer(user: ReturnType<typeof userEvent.setup>, name: string) {
    await user.click(
        within(screen.getByRole('alertdialog')).getByRole('button', { name }),
    );
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
}

describe('ChatThread', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(api.deleteSession).mockResolvedValue(undefined);
        URL.createObjectURL = vi.fn(() => 'blob:audio');
        URL.revokeObjectURL = vi.fn();
    });

    afterEach(() => {
        act(() => store().reset());
    });

    describe('空のとき', () => {
        it('新規チャットでは見出しとプリセットの選択と入力欄を出し、ヘッダは出さない', async () => {
            renderThread();
            await loadConfigs([friendly, voiced]);

            expect(screen.getByText('TALK')).toBeInTheDocument();
            expect(
                screen.getByRole('heading', { level: 1 }),
            ).toBeInTheDocument();
            expect(
                screen.getByRole('combobox', { name: 'プリセット' }),
            ).toHaveTextContent('フレンドリー');
            expect(composerInput()).toBeInTheDocument();
            expect(
                screen.queryByRole('button', { name: 'タイトルを編集' }),
            ).not.toBeInTheDocument();
        });

        it('プリセットの取得に失敗したら知らせて送信できないままにする', async () => {
            renderThread();
            vi.mocked(api.fetchConfigs).mockRejectedValueOnce(new Error('x'));
            await act(async () => {
                await store().loadConfigs();
            });

            expect(screen.getByRole('alert')).toHaveTextContent('プリセット');
            typeText(composerInput(), 'こんにちは');
            expect(screen.getByRole('button', { name: '送信' })).toBeDisabled();
        });

        it('メッセージのない既存のチャットではプリセットを固定で表示する', async () => {
            renderThread();
            await loadConfigs();
            await openSession([]);

            expect(screen.getByText('TALK')).toBeInTheDocument();
            expect(screen.getByText('フレンドリー')).toBeInTheDocument();
            expect(
                screen.queryByRole('combobox', { name: 'プリセット' }),
            ).not.toBeInTheDocument();
        });
    });

    describe('ヘッダ', () => {
        it('タイトルと固定のプリセットを表示し、h1 は 1 つにする', async () => {
            renderThread();
            await loadConfigs();
            await openSession();

            expect(screen.getByText('朝の挨拶')).toBeInTheDocument();
            expect(screen.getByText('フレンドリー')).toBeInTheDocument();
            expect(
                screen.queryByRole('combobox', { name: 'プリセット' }),
            ).not.toBeInTheDocument();
            expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(
                1,
            );
        });

        it('プリセットの一覧になければ識別子を表示する', async () => {
            renderThread();
            await openSession();

            expect(screen.getByText('friendly')).toBeInTheDocument();
        });

        it('タイトルを編集できる', async () => {
            const { user } = renderThread();
            await openSession();
            vi.mocked(api.updateSessionTitle).mockResolvedValueOnce(
                detail([], { title: '新しい題' }),
            );

            await user.click(
                screen.getByRole('button', { name: 'タイトルを編集' }),
            );
            const input = screen.getByRole('textbox', { name: 'タイトル' });
            await user.clear(input);
            await user.type(input, '新しい題{Enter}');

            await waitFor(() => {
                expect(api.updateSessionTitle).toHaveBeenCalledWith(
                    's1',
                    '新しい題',
                );
            });
            expect(await screen.findByText('新しい題')).toBeInTheDocument();
        });

        it('音声がなければ一括操作を出さない', async () => {
            renderThread();
            await openSession();

            expect(
                screen.queryByRole('button', { name: '音声を全削除' }),
            ).not.toBeInTheDocument();
        });
    });

    describe('入力欄', () => {
        it('Enter で送信し、入力欄を空にする', async () => {
            renderThread();
            await openSession();
            nextStreamMessage(controlledStream());
            typeText(composerInput(), 'こんにちは');

            fireEvent.keyDown(composerInput(), { key: 'Enter' });

            await waitFor(() => {
                expect(api.streamMessage).toHaveBeenCalledWith(
                    's1',
                    'こんにちは',
                    expect.anything(),
                );
            });
            expect(composerInput().value).toBe('');
        });

        it('送信ボタンで送信する', async () => {
            const { user } = renderThread();
            await openSession();
            nextStreamMessage(controlledStream());
            typeText(composerInput(), 'こんにちは');

            await user.click(screen.getByRole('button', { name: '送信' }));

            await waitFor(() => {
                expect(api.streamMessage).toHaveBeenCalledTimes(1);
            });
        });

        it('Shift+Enter では送信しない', async () => {
            renderThread();
            await openSession();
            typeText(composerInput(), 'こんにちは');

            fireEvent.keyDown(composerInput(), {
                key: 'Enter',
                shiftKey: true,
            });

            expect(api.streamMessage).not.toHaveBeenCalled();
            expect(composerInput().value).toBe('こんにちは');
        });

        it.each([
            ['isComposing', { isComposing: true }],
            ['keyCode 229', { keyCode: 229 }],
        ])('IME の確定の Enter（%s）では送信しない', async (_name, init) => {
            renderThread();
            await openSession();
            typeText(composerInput(), 'こんにちは');

            fireEvent.keyDown(composerInput(), { key: 'Enter', ...init });

            expect(api.streamMessage).not.toHaveBeenCalled();
            expect(composerInput().value).toBe('こんにちは');
        });

        it('空白だけでは送信しない', async () => {
            renderThread();
            await openSession();
            typeText(composerInput(), '   ');

            fireEvent.keyDown(composerInput(), { key: 'Enter' });

            expect(api.streamMessage).not.toHaveBeenCalled();
        });

        it('文字数を表示し、4000 字を超えたら送信を止めて本文を保つ', async () => {
            renderThread();
            await openSession();
            const tooLong = 'あ'.repeat(4001);

            typeText(composerInput(), tooLong);

            expect(screen.getByText('4001 / 4000')).toBeInTheDocument();
            expect(screen.getByRole('button', { name: '送信' })).toBeDisabled();
            fireEvent.keyDown(composerInput(), { key: 'Enter' });
            await act(async () => {});
            expect(api.streamMessage).not.toHaveBeenCalled();
            expect(composerInput().value).toBe(tooLong);
        });

        it('4000 字ちょうどなら送信できる', async () => {
            renderThread();
            await openSession();
            nextStreamMessage(controlledStream());
            typeText(composerInput(), 'あ'.repeat(4000));

            fireEvent.keyDown(composerInput(), { key: 'Enter' });

            await waitFor(() => {
                expect(api.streamMessage).toHaveBeenCalledTimes(1);
            });
        });

        // maxLength は貼り付けを黙って切ってしまう
        it('maxLength を付けない', async () => {
            renderThread();
            await openSession();

            expect(composerInput()).not.toHaveAttribute('maxlength');
        });

        it('生成中は停止ボタンに替わり、押すと停止する', async () => {
            const { user } = renderThread();
            await openSession();
            nextStreamMessage(controlledStream());
            typeText(composerInput(), 'こんにちは');
            fireEvent.keyDown(composerInput(), { key: 'Enter' });
            const stop = await screen.findByRole('button', { name: '停止' });
            expect(
                screen.queryByRole('button', { name: '送信' }),
            ).not.toBeInTheDocument();
            vi.mocked(api.getSession).mockImplementation(
                () => new Promise(() => {}),
            );

            await user.click(stop);

            await waitFor(() => {
                expect(store().isRunning).toBe(false);
            });
            expect(store().isSyncing).toBe(true);
            expect(screen.getByRole('button', { name: '送信' })).toBeDisabled();
            expect(screen.getByRole('status')).toHaveTextContent('確認');
        });

        it('生成中の Enter では改行を入れない', async () => {
            renderThread();
            await openSession();
            nextStreamMessage(controlledStream());
            typeText(composerInput(), '1 件目');
            fireEvent.keyDown(composerInput(), { key: 'Enter' });
            await screen.findByRole('button', { name: '停止' });
            typeText(composerInput(), '続きの下書き');

            const notPrevented = fireEvent.keyDown(composerInput(), {
                key: 'Enter',
            });

            expect(notPrevented).toBe(false);
            expect(api.streamMessage).toHaveBeenCalledTimes(1);
            expect(composerInput().value).toBe('続きの下書き');
        });
    });

    describe('バナー', () => {
        it('失敗の文言を出し、閉じられる', async () => {
            const { user } = renderThread();
            await openSession();
            const stream = controlledStream();
            nextStreamMessage(stream);
            typeText(composerInput(), 'こんにちは');
            fireEvent.keyDown(composerInput(), { key: 'Enter' });
            await waitFor(() => {
                expect(api.streamMessage).toHaveBeenCalled();
            });

            await push(stream, {
                type: 'error',
                status: 502,
                error: 'LLM に接続できません',
            });

            expect(await screen.findByRole('alert')).toHaveTextContent(
                'LLM に接続できません',
            );
            await waitFor(() => {
                expect(composerInput().value).toBe('こんにちは');
            });

            await user.click(
                screen.getByRole('button', { name: 'メッセージを閉じる' }),
            );

            expect(screen.queryByRole('alert')).not.toBeInTheDocument();
        });

        it('50 件に達したら送信を止め、新しいチャットへの導線を出す', async () => {
            renderThread();
            const fifty = Array.from({ length: 50 }, (_, i) =>
                i % 2 === 0
                    ? userMessage({ id: i + 1, sequence: i })
                    : assistantMessage({ id: i + 1, sequence: i }),
            );
            await openSession(fifty);
            typeText(composerInput(), 'こんにちは');

            expect(screen.getByRole('status')).toHaveTextContent('上限');
            expect(
                screen.getByRole('link', { name: '新しいチャット' }),
            ).toHaveAttribute('href', '/talk');
            expect(screen.getByRole('button', { name: '送信' })).toBeDisabled();
        });

        it('49 件なら上限の案内を出さない', async () => {
            renderThread();
            const history = Array.from({ length: 49 }, (_, i) =>
                i % 2 === 0
                    ? userMessage({ id: i + 1, sequence: i })
                    : assistantMessage({ id: i + 1, sequence: i }),
            );
            await openSession(history);

            expect(
                screen.queryByRole('link', { name: '新しいチャット' }),
            ).not.toBeInTheDocument();
        });
    });

    describe('メッセージの表示', () => {
        it('発話は Markdown として解釈せずそのまま表示する', async () => {
            renderThread();
            await openSession([userMessage({ content: '**太字**\n改行' })]);

            const text = screen.getByText(/\*\*太字\*\*/);
            expect(text.textContent).toBe('**太字**\n改行');
            expect(document.querySelector('strong')).toBeNull();
        });

        it('応答は Markdown として表示する', async () => {
            renderThread();
            await openSession([
                userMessage(),
                assistantMessage({
                    content:
                        '**太字**\n\n| 列 |\n| --- |\n| 値 |\n\n`inline`\n\n```python\nprint(1)\n```',
                }),
            ]);

            await waitFor(() => {
                expect(screen.getByText('太字').tagName).toBe('STRONG');
            });
            expect(screen.getByRole('table')).toBeInTheDocument();
            expect(screen.getByText('inline').tagName).toBe('CODE');
            expect(screen.getByText('python')).toBeInTheDocument();
            expect(screen.getByText('print(1)').closest('pre')).not.toBeNull();
            expect(
                screen.getByRole('button', { name: 'コードをコピー' }),
            ).toBeInTheDocument();
        });

        it('応答の改行をそのまま改行として表示する', async () => {
            renderThread();
            await openSession([
                userMessage(),
                assistantMessage({ content: '1 行目\n2 行目' }),
            ]);

            await waitFor(() => {
                expect(document.querySelector('br')).not.toBeNull();
            });
        });

        it('生の HTML を描画しない', async () => {
            renderThread();
            await openSession([
                userMessage(),
                assistantMessage({
                    content:
                        '<img src="x" onerror="alert(1)"><script>alert(2)</script><b>太</b>\n\n本文',
                }),
            ]);

            await screen.findByText('本文');
            expect(document.querySelector('img')).toBeNull();
            expect(document.querySelector('script')).toBeNull();
            expect(document.querySelector('b')).toBeNull();
        });

        it('javascript: のリンクを無効にする', async () => {
            renderThread();
            await openSession([
                userMessage(),
                assistantMessage({ content: '[押す](javascript:alert(1))' }),
            ]);

            const link = await screen.findByText('押す');
            expect(link.getAttribute('href') ?? '').not.toContain('javascript');
        });

        it('リンクを別タブで開く', async () => {
            renderThread();
            await openSession([
                userMessage(),
                assistantMessage({ content: '[鍵山](https://example.com/)' }),
            ]);

            const link = await screen.findByRole('link', { name: '鍵山' });
            expect(link).toHaveAttribute('target', '_blank');
            expect(link).toHaveAttribute('rel', 'noreferrer noopener');
        });

        it('Markdown の画像は読み込まずリンクにする', async () => {
            renderThread();
            await openSession([
                userMessage(),
                assistantMessage({
                    content: '![代替文](https://example.com/x.png)',
                }),
            ]);

            const link = await screen.findByRole('link', { name: '代替文' });
            expect(link).toHaveAttribute('href', 'https://example.com/x.png');
            expect(document.querySelector('img')).toBeNull();
        });

        it('停止した応答に印を出す', async () => {
            renderThread();
            await openSession([]);
            const stream = controlledStream();
            nextStreamMessage(stream);
            typeText(composerInput(), 'こんにちは');
            fireEvent.keyDown(composerInput(), { key: 'Enter' });
            await waitFor(() => {
                expect(api.streamMessage).toHaveBeenCalled();
            });
            await push(stream, { type: 'delta', text: '途中' });
            vi.mocked(api.getSession).mockImplementation(
                () => new Promise(() => {}),
            );

            act(() => store().cancelRun());

            expect(
                await screen.findByText('ここで停止しました'),
            ).toBeInTheDocument();
        });
    });

    describe('アクション', () => {
        it('最後の応答にコピーと再生成、発話に編集を出す', async () => {
            renderThread();
            await openSession([
                userMessage(),
                assistantMessage(),
                userMessage({ id: 3, sequence: 2 }),
                assistantMessage({ id: 4, sequence: 3 }),
            ]);

            expect(
                screen.getAllByRole('button', { name: '編集' }),
            ).toHaveLength(2);
            expect(
                screen.getAllByRole('button', { name: 'コピー' }),
            ).toHaveLength(2);
            // 古い応答の再生成は以降の履歴を黙って消すので、最後の応答にだけ出す
            expect(
                screen.getAllByRole('button', { name: '再生成' }),
            ).toHaveLength(1);
        });

        it('生成中はアクションを隠す', async () => {
            renderThread();
            await openSession();
            nextStreamMessage(controlledStream());
            typeText(composerInput(), 'こんにちは');
            fireEvent.keyDown(composerInput(), { key: 'Enter' });
            await screen.findByRole('button', { name: '停止' });

            expect(
                screen.queryByRole('button', { name: '編集' }),
            ).not.toBeInTheDocument();
            expect(
                screen.queryByRole('button', { name: '再生成' }),
            ).not.toBeInTheDocument();
        });

        it('同期中はアクションを隠す', async () => {
            renderThread();
            await openSession();
            nextStreamMessage(controlledStream());
            typeText(composerInput(), 'こんにちは');
            fireEvent.keyDown(composerInput(), { key: 'Enter' });
            await screen.findByRole('button', { name: '停止' });
            vi.mocked(api.getSession).mockImplementation(
                () => new Promise(() => {}),
            );

            act(() => store().cancelRun());

            await waitFor(() => {
                expect(store().isRunning).toBe(false);
            });
            expect(
                screen.queryByRole('button', { name: '編集' }),
            ).not.toBeInTheDocument();
            expect(
                screen.queryByRole('button', { name: '再生成' }),
            ).not.toBeInTheDocument();
        });

        it('再生成を押すと直前の発話を送り直す', async () => {
            const { user } = renderThread();
            await openSession();
            nextStreamEdit(controlledStream());

            await user.click(screen.getByRole('button', { name: '再生成' }));

            await waitFor(() => {
                expect(api.streamEdit).toHaveBeenCalledWith(
                    's1',
                    1,
                    'おはよう',
                    expect.anything(),
                );
            });
        });

        it('編集を開いて送信し、文字数の上限を超えたら止める', async () => {
            const { user } = renderThread();
            await openSession();
            nextStreamEdit(controlledStream());

            await user.click(screen.getByRole('button', { name: '編集' }));
            const input = screen.getByRole('textbox', {
                name: 'メッセージを編集',
            }) as HTMLTextAreaElement;
            expect(input.value).toBe('おはよう');
            expect(
                screen.getByRole('button', { name: '送信して置き換える' }),
            ).toBeDisabled();
            expect(
                screen.getByText(/以降の履歴は置き換わります/),
            ).toBeInTheDocument();

            typeText(input, 'あ'.repeat(4001));
            expect(
                screen.getByRole('button', { name: '送信して置き換える' }),
            ).toBeDisabled();
            fireEvent.keyDown(input, { key: 'Enter' });
            await act(async () => {});
            expect(api.streamEdit).not.toHaveBeenCalled();

            typeText(input, '直した');
            await user.click(
                screen.getByRole('button', { name: '送信して置き換える' }),
            );

            await waitFor(() => {
                expect(api.streamEdit).toHaveBeenCalledWith(
                    's1',
                    1,
                    '直した',
                    expect.anything(),
                );
            });
        });

        it('本文を変えずに Enter を押しても送らない', async () => {
            const { user } = renderThread();
            await openSession();

            await user.click(screen.getByRole('button', { name: '編集' }));
            fireEvent.keyDown(
                screen.getByRole('textbox', { name: 'メッセージを編集' }),
                { key: 'Enter' },
            );
            await act(async () => {});

            expect(api.streamEdit).not.toHaveBeenCalled();
        });

        it('編集をキャンセルすると元の表示へ戻る', async () => {
            const { user } = renderThread();
            await openSession();

            await user.click(screen.getByRole('button', { name: '編集' }));
            await user.click(
                screen.getByRole('button', { name: 'キャンセル' }),
            );

            expect(
                screen.queryByRole('textbox', { name: 'メッセージを編集' }),
            ).not.toBeInTheDocument();
            expect(screen.getByText('おはよう')).toBeInTheDocument();
            expect(api.streamEdit).not.toHaveBeenCalled();
        });
    });

    describe('音声', () => {
        const withAudio = [
            userMessage(),
            assistantMessage({
                audio_url: '/talk/sessions/s1/audio/2/',
                audio_format: 'wav',
                audio_size_bytes: 2048,
            }),
        ];

        beforeEach(() => {
            vi.mocked(api.fetchAudioBlob).mockResolvedValue(
                new Blob(['x'], { type: 'audio/wav' }),
            );
        });

        it('音声があれば取得してプレーヤーとサイズとダウンロードを出す', async () => {
            renderThread();
            await openSession(withAudio);

            expect(
                await screen.findByRole('button', { name: '再生' }),
            ).toBeInTheDocument();
            expect(api.fetchAudioBlob).toHaveBeenCalledWith('s1', 2);
            expect(screen.getByText('2.0 KB')).toBeInTheDocument();
            expect(
                screen.getByRole('button', { name: 'ダウンロード' }),
            ).toBeInTheDocument();
        });

        it('音声を取得できなければ文言を出す', async () => {
            vi.mocked(api.fetchAudioBlob).mockRejectedValue(new Error('x'));
            renderThread();
            await openSession(withAudio);

            expect(
                await screen.findByText('音声の取得に失敗しました'),
            ).toBeInTheDocument();
        });

        it('合成中と失敗の表示を出す', async () => {
            vi.mocked(api.fetchConfigs).mockResolvedValueOnce([voiced]);
            renderThread();
            await act(async () => {
                await store().loadConfigs();
            });
            await openSession([], { config_name: 'voiced' });
            const stream = controlledStream();
            nextStreamMessage(stream);
            typeText(composerInput(), 'こんにちは');
            fireEvent.keyDown(composerInput(), { key: 'Enter' });
            await waitFor(() => {
                expect(api.streamMessage).toHaveBeenCalled();
            });

            await push(stream, {
                type: 'message',
                user: userMessage({ id: 10, content: 'こんにちは' }),
                assistant: assistantMessage({ id: 11, content: '応答' }),
            });

            expect(screen.getByText('音声を合成中…')).toBeInTheDocument();

            await push(stream, {
                type: 'audio_error',
                message_id: 11,
                error: '合成サーバーに接続できません',
            });

            expect(
                screen.getByText('合成サーバーに接続できません'),
            ).toBeInTheDocument();
            expect(screen.queryByText('音声を合成中…')).not.toBeInTheDocument();
        });

        it('個別の削除はキャンセルすると消さない', async () => {
            const { user } = renderThread();
            await openSession(withAudio);

            await user.click(
                await screen.findByRole('button', { name: '音声を削除' }),
            );
            await answer(user, 'キャンセル');

            expect(api.deleteAudio).not.toHaveBeenCalled();
        });

        it('個別の削除は確定すると消す', async () => {
            const { user } = renderThread();
            await openSession(withAudio);
            vi.mocked(api.deleteAudio).mockResolvedValueOnce(undefined);

            await user.click(
                await screen.findByRole('button', { name: '音声を削除' }),
            );
            await answer(user, '削除');

            expect(api.deleteAudio).toHaveBeenCalledWith('s1', 2);
            await waitFor(() => {
                expect(
                    screen.queryByRole('button', { name: '再生' }),
                ).not.toBeInTheDocument();
            });
        });

        it('一括の削除はキャンセルすると消さない', async () => {
            const { user } = renderThread();
            await openSession(withAudio);

            await user.click(
                screen.getByRole('button', { name: '音声を全削除' }),
            );
            await answer(user, 'キャンセル');

            expect(api.bulkDeleteAudio).not.toHaveBeenCalled();
        });

        it('一括の削除は確定すると消し、一括操作を隠す', async () => {
            const { user } = renderThread();
            await openSession(withAudio);
            vi.mocked(api.bulkDeleteAudio).mockResolvedValueOnce(undefined);

            await user.click(
                screen.getByRole('button', { name: '音声を全削除' }),
            );
            await answer(user, '全て削除');

            expect(api.bulkDeleteAudio).toHaveBeenCalledWith('s1');
            await waitFor(() => {
                expect(
                    screen.queryByRole('button', { name: '音声を全削除' }),
                ).not.toBeInTheDocument();
            });
        });

        it('一括の再生とダウンロードの件数を出す', async () => {
            renderThread();
            await openSession(withAudio);

            expect(
                screen.getByRole('button', { name: /一括再生 \(1\)/ }),
            ).toBeEnabled();
            expect(
                screen.getByRole('button', { name: /一括 DL \(1\)/ }),
            ).toBeEnabled();
        });
    });
});
