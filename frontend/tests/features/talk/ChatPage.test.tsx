import {
    act,
    fireEvent,
    render,
    screen,
    waitFor,
} from '@testing-library/react';
import { HTTPError, type NormalizedOptions } from 'ky';
import { Link, MemoryRouter, Route, Routes, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatPage } from '@/features/talk/ChatPage';
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
    fetchSettings: vi.fn(),
    getSession: vi.fn(),
    listSessions: vi.fn(),
    streamEdit: vi.fn(),
    streamMessage: vi.fn(),
    updateSessionTitle: vi.fn(),
}));

const NOW = '2026-11-02T09:30:00+09:00';

const greeting: ChatSessionMessage = {
    id: 1,
    sequence: 0,
    role: 'user',
    content: 'おはよう',
    audio_url: null,
    audio_format: '',
    audio_size_bytes: 0,
    created_at: NOW,
};

function detail(
    messages: readonly ChatSessionMessage[] = [],
    overrides: Partial<ChatSessionDetail> = {},
): ChatSessionDetail {
    return {
        id: 's1',
        title: '朝の挨拶',
        setting: { id: 1, name: 'フレンドリー' },
        skill: null,
        tts_enabled: false,
        message_count: messages.length,
        total_audio_bytes: 0,
        created_at: NOW,
        updated_at: NOW,
        messages,
        ...overrides,
    };
}

const store = () => useChatStore.getState();

function LocationProbe() {
    const { pathname } = useLocation();
    return <output data-testid="pathname">{pathname}</output>;
}

function renderPage(path: string) {
    return render(
        <MemoryRouter initialEntries={[path]}>
            <nav>
                <Link to="/talk">新規へ</Link>
                <Link to="/talk/s2">s2 へ</Link>
                <Link to="/other">他のページへ</Link>
            </nav>
            <Routes>
                <Route path="/talk/:sessionId?" element={<ChatPage />} />
                <Route path="/other" element={<p>他のページ</p>} />
            </Routes>
            <LocationProbe />
        </MemoryRouter>,
    );
}

const composerInput = () =>
    screen.getByRole('textbox', { name: 'メッセージ' }) as HTMLTextAreaElement;

function nextStreamMessage(stream: ControlledStream) {
    vi.mocked(api.streamMessage).mockImplementationOnce((_id, _content, opts) =>
        stream.generator(opts?.signal),
    );
}

describe('ChatPage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(api.deleteSession).mockResolvedValue(undefined);
        vi.mocked(api.listSessions).mockResolvedValue({
            count: 0,
            next: null,
            previous: null,
            results: [],
        });
        vi.mocked(api.fetchSettings).mockResolvedValue([
            { id: 1, name: 'フレンドリー', tts_enabled: false, skills: [] },
        ]);
    });

    afterEach(() => {
        act(() => store().reset());
    });

    it('一覧と Talk 設定を読み込み、ページを離れるとストアを片付ける', async () => {
        renderPage('/talk');

        await waitFor(() => {
            expect(store().selectedSettingId).toBe(1);
        });
        expect(api.fetchSettings).toHaveBeenCalledTimes(1);
        expect(api.listSessions).toHaveBeenCalledTimes(1);

        fireEvent.click(screen.getByRole('link', { name: '他のページへ' }));

        expect(await screen.findByText('他のページ')).toBeInTheDocument();
        expect(store().settings).toBeNull();
    });

    it('/talk では新規チャットを出し、h1 は 1 つにする', async () => {
        renderPage('/talk');

        expect(await screen.findByText('TALK')).toBeInTheDocument();
        expect(store().activeSessionId).toBeNull();
        expect(api.getSession).not.toHaveBeenCalled();
        expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    });

    it('URL のセッションを復元する', async () => {
        vi.mocked(api.getSession).mockResolvedValueOnce(detail([greeting]));

        renderPage('/talk/s1');

        expect(await screen.findByText('おはよう')).toBeInTheDocument();
        expect(api.getSession).toHaveBeenCalledWith('s1');
        expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    });

    it('読み込み中は新規チャットの画面を出さない', () => {
        vi.mocked(api.getSession).mockImplementationOnce(
            () => new Promise(() => {}),
        );

        renderPage('/talk/s1');

        expect(screen.queryByText('TALK')).not.toBeInTheDocument();
        expect(
            screen.getByRole('status', { name: '読み込み中' }),
        ).toBeInTheDocument();
    });

    // react-router は %2F を / に戻すので、そのまま API のパスに入ると別の API を呼ばれる
    it('細工したリンクでは API を呼ばずに /talk へ移る', async () => {
        renderPage('/talk/..%2F..%2Fhn-agent%2Frun-all%2F%3F');

        await waitFor(() => {
            expect(screen.getByTestId('pathname').textContent).toBe('/talk');
        });
        expect(api.getSession).not.toHaveBeenCalled();
        expect(store().activeSessionId).toBeNull();
        expect(screen.getByRole('alert')).toHaveTextContent(
            'チャットが見つかりません',
        );
    });

    describe('読み込みの失敗', () => {
        async function failToLoad() {
            vi.mocked(api.getSession).mockRejectedValueOnce(
                new TypeError('Failed to fetch'),
            );
            renderPage('/talk/s1');
            await screen.findByRole('button', { name: '再読み込み' });
        }

        it('新規チャットに見せず、送信を止めて再読み込みの導線を出す', async () => {
            await failToLoad();

            expect(screen.queryByText('TALK')).not.toBeInTheDocument();
            expect(
                screen.queryByRole('combobox', { name: 'Talk 設定' }),
            ).not.toBeInTheDocument();
            expect(screen.getByRole('alert')).toHaveTextContent(
                'チャットの読み込みに失敗しました',
            );
            expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(
                1,
            );
            fireEvent.change(composerInput(), {
                target: { value: '送れないはず' },
            });
            expect(screen.getByRole('button', { name: '送信' })).toBeDisabled();
        });

        it('再読み込みすると会話を表示して送信できるようになる', async () => {
            await failToLoad();
            vi.mocked(api.getSession).mockResolvedValueOnce(detail([greeting]));

            fireEvent.click(screen.getByRole('button', { name: '再読み込み' }));

            expect(await screen.findByText('おはよう')).toBeInTheDocument();
            expect(screen.queryByRole('alert')).not.toBeInTheDocument();
            fireEvent.change(composerInput(), {
                target: { value: 'こんにちは' },
            });
            expect(screen.getByRole('button', { name: '送信' })).toBeEnabled();
        });

        it('再読み込みでも見つからなければ /talk へ移る', async () => {
            await failToLoad();
            vi.mocked(api.getSession).mockRejectedValueOnce(
                new HTTPError(
                    new Response(null, { status: 404 }),
                    new Request('http://localhost/api/x'),
                    {} as NormalizedOptions,
                ),
            );

            fireEvent.click(screen.getByRole('button', { name: '再読み込み' }));

            await waitFor(() => {
                expect(screen.getByTestId('pathname').textContent).toBe(
                    '/talk',
                );
            });
        });
    });

    it('存在しないセッションなら /talk へ移ってバナーで知らせる', async () => {
        vi.mocked(api.getSession).mockRejectedValueOnce(
            new HTTPError(
                new Response(null, { status: 404 }),
                new Request('http://localhost/api/x'),
                {} as NormalizedOptions,
            ),
        );

        renderPage('/talk/gone');

        await waitFor(() => {
            expect(screen.getByTestId('pathname').textContent).toBe('/talk');
        });
        expect(screen.getByRole('alert')).toHaveTextContent(
            'チャットが見つかりません',
        );
        expect(await screen.findByText('TALK')).toBeInTheDocument();
    });

    it('別のセッションへ移ると入力欄を空にして読み込み直す', async () => {
        vi.mocked(api.getSession).mockResolvedValueOnce(detail([greeting]));
        renderPage('/talk/s1');
        await screen.findByText('おはよう');
        fireEvent.change(composerInput(), { target: { value: '下書き' } });
        vi.mocked(api.getSession).mockResolvedValueOnce(
            detail([{ ...greeting, id: 9, content: 'こんばんは' }], {
                id: 's2',
            }),
        );

        fireEvent.click(screen.getByRole('link', { name: 's2 へ' }));

        expect(await screen.findByText('こんばんは')).toBeInTheDocument();
        expect(composerInput().value).toBe('');
    });

    it('新規チャットへ移ると表示を空にする', async () => {
        vi.mocked(api.getSession).mockResolvedValueOnce(detail([greeting]));
        renderPage('/talk/s1');
        await screen.findByText('おはよう');

        fireEvent.click(screen.getByRole('link', { name: '新規へ' }));

        expect(await screen.findByText('TALK')).toBeInTheDocument();
        expect(screen.queryByText('おはよう')).not.toBeInTheDocument();
    });

    describe('最初の送信', () => {
        async function sendFirstMessage() {
            renderPage('/talk');
            await waitFor(() => {
                expect(store().selectedSettingId).toBe(1);
            });
            const input = composerInput();
            vi.mocked(api.createSession).mockResolvedValueOnce(
                detail([], { id: 'new', title: '' }),
            );
            const stream = controlledStream();
            nextStreamMessage(stream);
            fireEvent.change(input, { target: { value: 'こんにちは' } });
            fireEvent.keyDown(input, { key: 'Enter' });
            await waitFor(() => {
                expect(screen.getByTestId('pathname').textContent).toBe(
                    '/talk/new',
                );
            });
            expect(api.createSession).toHaveBeenCalledWith(1, null);
            return { input, stream };
        }

        // 遅延作成で URL が変わっても、入力欄と行がリマウントしない
        it('セッションの URL へ移っても画面を作り直さない', async () => {
            const { input } = await sendFirstMessage();

            expect(composerInput()).toBe(input);
            expect(screen.getByText('こんにちは')).toBeInTheDocument();
            expect(api.getSession).not.toHaveBeenCalled();
            expect(screen.queryByText('TALK')).not.toBeInTheDocument();
        });

        it('失敗すると /talk へ戻り、入力文を入力欄へ戻す', async () => {
            const { input, stream } = await sendFirstMessage();

            await act(async () => {
                stream.push({ type: 'error', status: 502, error: '失敗' });
                await new Promise((resolve) => setTimeout(resolve, 0));
            });

            await waitFor(() => {
                expect(screen.getByTestId('pathname').textContent).toBe(
                    '/talk',
                );
                expect(composerInput().value).toBe('こんにちは');
            });
            expect(composerInput()).toBe(input);
            expect(api.deleteSession).toHaveBeenCalledWith('new');
            expect(screen.getByRole('alert')).toHaveTextContent('失敗');
        });
    });
});
