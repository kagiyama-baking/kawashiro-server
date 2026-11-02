import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SessionNav } from '@/features/talk/SessionNav';
import * as api from '@/lib/api/talk';
import { useChatStore } from '@/stores/chat-store';
import type { ChatSessionListItem } from '@/types/talk';

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

function item(
    overrides: Partial<ChatSessionListItem> = {},
): ChatSessionListItem {
    return {
        id: 's1',
        title: '朝の挨拶',
        config_name: 'friendly',
        message_count: 2,
        total_audio_bytes: 2048,
        created_at: NOW,
        updated_at: NOW,
        ...overrides,
    };
}

const store = () => useChatStore.getState();

function LocationProbe() {
    const { pathname } = useLocation();
    return <output data-testid="pathname">{pathname}</output>;
}

function renderNav(path = '/talk', onNavigate = vi.fn()) {
    render(
        <MemoryRouter initialEntries={[path]}>
            <SessionNav onNavigate={onNavigate} />
            <LocationProbe />
        </MemoryRouter>,
    );
    return { user: userEvent.setup(), onNavigate };
}

async function loadList(
    sessions: readonly ChatSessionListItem[],
    next: string | null = null,
) {
    vi.mocked(api.listSessions).mockResolvedValueOnce({
        count: sessions.length,
        next,
        previous: null,
        results: sessions,
    });
    await act(async () => {
        await store().loadSessions();
    });
}

async function answer(user: ReturnType<typeof userEvent.setup>, name: string) {
    await user.click(
        within(screen.getByRole('alertdialog')).getByRole('button', { name }),
    );
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
}

describe('SessionNav', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(api.deleteSession).mockResolvedValue(undefined);
    });

    afterEach(() => {
        act(() => store().reset());
    });

    it('新しいチャットのリンクを出し、/talk にいるときは現在地にする', () => {
        renderNav('/talk');

        const link = screen.getByRole('link', { name: '新しいチャット' });
        expect(link).toHaveAttribute('href', '/talk');
        expect(link).toHaveAttribute('aria-current', 'page');
    });

    it('セッションを選んでいるときは新しいチャットを現在地にしない', () => {
        renderNav('/talk/s1');

        expect(
            screen.getByRole('link', { name: '新しいチャット' }),
        ).not.toHaveAttribute('aria-current');
    });

    it('セッションをリンクで並べ、題、件数、音声のサイズを出す', async () => {
        renderNav('/talk/s1');
        await loadList([item(), item({ id: 's2', title: '' })]);

        const active = screen.getByRole('link', { name: /朝の挨拶/ });
        expect(active).toHaveAttribute('href', '/talk/s1');
        expect(active).toHaveAttribute('aria-current', 'page');
        expect(within(active).getByText(/2 件/)).toBeInTheDocument();
        expect(within(active).getByText(/2\.0 KB/)).toBeInTheDocument();

        const untitled = screen.getByRole('link', { name: /（無題）/ });
        expect(untitled).toHaveAttribute('href', '/talk/s2');
        expect(untitled).not.toHaveAttribute('aria-current');
    });

    // 以前は button の中に button があり、HTML として不正だった
    it('リンクの中に削除ボタンを入れない', async () => {
        renderNav('/talk');
        await loadList([item()]);

        const link = screen.getByRole('link', { name: /朝の挨拶/ });
        expect(within(link).queryByRole('button')).not.toBeInTheDocument();
    });

    it('履歴がなければそう表示する', () => {
        renderNav('/talk');

        expect(screen.getByText('まだ履歴がありません')).toBeInTheDocument();
    });

    it('読み込み中は「まだ履歴がありません」を出さない', async () => {
        renderNav('/talk');
        vi.mocked(api.listSessions).mockImplementationOnce(
            () => new Promise(() => {}),
        );

        act(() => {
            void store().loadSessions();
        });

        expect(
            screen.queryByText('まだ履歴がありません'),
        ).not.toBeInTheDocument();
    });

    it('リンクを押すと遷移して onNavigate を呼ぶ', async () => {
        const { user, onNavigate } = renderNav('/talk');
        await loadList([item()]);

        await user.click(screen.getByRole('link', { name: /朝の挨拶/ }));

        expect(screen.getByTestId('pathname')).toHaveTextContent('/talk/s1');
        expect(onNavigate).toHaveBeenCalledTimes(1);
    });

    it('続きがあれば読み込める', async () => {
        const { user } = renderNav('/talk');
        await loadList([item()], 'next');
        vi.mocked(api.listSessions).mockResolvedValueOnce({
            count: 2,
            next: null,
            previous: null,
            results: [item({ id: 's2', title: '次の話' })],
        });

        await user.click(
            screen.getByRole('button', { name: 'もっと読み込む' }),
        );

        expect(
            await screen.findByRole('link', { name: /次の話/ }),
        ).toBeInTheDocument();
        expect(
            screen.queryByRole('button', { name: 'もっと読み込む' }),
        ).not.toBeInTheDocument();
    });

    describe('削除', () => {
        const deleteButton = () =>
            screen.getByRole('button', { name: '「朝の挨拶」を削除' });

        it('キャンセルすると削除しない', async () => {
            const { user } = renderNav('/talk');
            await loadList([item()]);

            await user.click(deleteButton());
            await answer(user, 'キャンセル');

            expect(api.deleteSession).not.toHaveBeenCalled();
        });

        it('確定すると対象のセッションを削除する', async () => {
            const { user } = renderNav('/talk');
            await loadList([item()]);

            await user.click(deleteButton());
            await answer(user, '削除');

            await waitFor(() => {
                expect(api.deleteSession).toHaveBeenCalledWith('s1');
            });
            await waitFor(() => {
                expect(
                    screen.queryByRole('link', { name: /朝の挨拶/ }),
                ).not.toBeInTheDocument();
            });
        });

        it('表示中のセッションを削除すると /talk へ移る', async () => {
            const { user } = renderNav('/talk/s1');
            await loadList([item()]);
            vi.mocked(api.getSession).mockResolvedValueOnce({
                ...item(),
                messages: [],
            });
            await act(async () => {
                await store().openSession('s1');
            });

            await user.click(deleteButton());
            await answer(user, '削除');

            await waitFor(() => {
                expect(screen.getByTestId('pathname').textContent).toBe(
                    '/talk',
                );
            });
        });

        it('別のセッションを見ているときは移らない', async () => {
            const { user } = renderNav('/talk/s2');
            await loadList([item(), item({ id: 's2', title: '別' })]);

            await user.click(deleteButton());
            await answer(user, '削除');

            await waitFor(() => {
                expect(api.deleteSession).toHaveBeenCalledWith('s1');
            });
            expect(screen.getByTestId('pathname').textContent).toBe('/talk/s2');
        });

        it('失敗したらバナーで知らせて一覧に残す', async () => {
            const { user } = renderNav('/talk');
            await loadList([item()]);
            vi.mocked(api.deleteSession).mockRejectedValueOnce(new Error('x'));

            await user.click(deleteButton());
            await answer(user, '削除');

            await waitFor(() => {
                expect(store().error).toBe('チャットを削除できませんでした');
            });
            expect(
                screen.getByRole('link', { name: /朝の挨拶/ }),
            ).toBeInTheDocument();
        });
    });
});
