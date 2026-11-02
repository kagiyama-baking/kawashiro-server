import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';
import { Sidebar } from '@/components/layout/Sidebar';
import { useAuthStore } from '@/stores/auth-store';

const NAV_ITEMS = [
    { to: '/', en: 'Home', ja: 'ホーム' },
    { to: '/tts', en: 'Voice', ja: 'テキスト読み上げ' },
    { to: '/talk', en: 'Talk', ja: 'チャット' },
    { to: '/media', en: 'Media', ja: 'メディア変換' },
    { to: '/pdf-edit', en: 'PDF', ja: 'PDF編集' },
] as const;

function LocationProbe() {
    const { pathname } = useLocation();
    return <output data-testid="pathname">{pathname}</output>;
}

function renderSidebar(initialPath = '/') {
    return render(
        <MemoryRouter initialEntries={[initialPath]}>
            <Sidebar />
            <LocationProbe />
        </MemoryRouter>,
    );
}

// jsdom は CSS を解決しないので、ドロワーとデスクトップの 2 つの aside がどちらも見える
function drawer() {
    return screen.getAllByRole('complementary')[0];
}

function desktop() {
    return within(screen.getAllByRole('complementary')[1]);
}

describe('Sidebar', () => {
    beforeEach(() => {
        useAuthStore.setState({
            token: 'test-token',
            email: 'user@example.com',
            isAuthenticated: true,
        });
    });

    describe('ナビゲーション', () => {
        it.each(NAV_ITEMS)(
            '$ja のリンクに EN と JA の 2 段ラベルを表示する',
            ({ to, en, ja }) => {
                renderSidebar();

                const link = desktop().getByRole('link', {
                    name: new RegExp(ja),
                });
                expect(link).toHaveAttribute('href', to);
                expect(within(link).getByText(en)).toBeInTheDocument();
                expect(within(link).getByText(ja)).toBeInTheDocument();
            },
        );

        it('現在のページのリンクにだけ aria-current を付ける', () => {
            renderSidebar('/tts');

            expect(
                desktop().getByRole('link', { name: /テキスト読み上げ/ }),
            ).toHaveAttribute('aria-current', 'page');
            ['ホーム', 'チャット', 'メディア変換', 'PDF編集'].forEach((ja) => {
                expect(
                    desktop().getByRole('link', { name: new RegExp(ja) }),
                ).not.toHaveAttribute('aria-current');
            });
        });

        it('トップにいるときはホームを現在地にする', () => {
            renderSidebar('/');

            expect(
                desktop().getByRole('link', { name: /ホーム/ }),
            ).toHaveAttribute('aria-current', 'page');
        });
    });

    describe('ブランド', () => {
        it('ブランド名を表示し、ページの h1 と競合する見出しにはしない', () => {
            renderSidebar();

            expect(desktop().getByText('鍵山製パン')).toBeInTheDocument();
            expect(
                screen.queryByRole('heading', { level: 1 }),
            ).not.toBeInTheDocument();
        });
    });

    describe('アカウント', () => {
        it('メールアドレスとログアウトを表示する', () => {
            renderSidebar();

            expect(desktop().getByText('user@example.com')).toBeInTheDocument();
            expect(
                desktop().getByRole('button', { name: 'ログアウト' }),
            ).toBeInTheDocument();
        });

        it('ログアウトすると認証を消してログイン画面へ移る', async () => {
            const user = userEvent.setup();
            renderSidebar('/tts');

            await user.click(
                desktop().getByRole('button', { name: 'ログアウト' }),
            );

            expect(useAuthStore.getState().isAuthenticated).toBe(false);
            expect(screen.getByTestId('pathname')).toHaveTextContent('/login');
        });
    });

    describe('モバイルドロワー', () => {
        it('閉じている間はドロワーをフォーカスの対象から外す', () => {
            renderSidebar();

            expect(drawer()).toHaveAttribute('inert');
            expect(screen.getAllByRole('complementary')[1]).not.toHaveAttribute(
                'inert',
            );
        });

        it('メニューボタンで開き、閉じるボタンで閉じる', async () => {
            const user = userEvent.setup();
            renderSidebar();

            await user.click(
                screen.getByRole('button', { name: 'メニューを開く' }),
            );
            expect(drawer()).not.toHaveAttribute('inert');

            await user.click(
                within(drawer()).getByRole('button', {
                    name: 'メニューを閉じる',
                }),
            );
            expect(drawer()).toHaveAttribute('inert');
        });

        it('Esc キーで閉じる', async () => {
            const user = userEvent.setup();
            renderSidebar();

            await user.click(
                screen.getByRole('button', { name: 'メニューを開く' }),
            );
            expect(drawer()).not.toHaveAttribute('inert');

            await user.keyboard('{Escape}');

            expect(drawer()).toHaveAttribute('inert');
        });

        it('リンクを押すと閉じて遷移する', async () => {
            const user = userEvent.setup();
            renderSidebar();

            await user.click(
                screen.getByRole('button', { name: 'メニューを開く' }),
            );
            expect(drawer()).not.toHaveAttribute('inert');

            await user.click(
                within(drawer()).getByRole('link', { name: /メディア変換/ }),
            );

            expect(drawer()).toHaveAttribute('inert');
            expect(screen.getByTestId('pathname')).toHaveTextContent('/media');
        });

        // 閉じるとドロワー内の要素は inert になり、フォーカスが行き先を失う
        it('閉じるボタンで閉じるとメニューボタンへフォーカスを戻す', async () => {
            const user = userEvent.setup();
            renderSidebar();
            const menuButton = screen.getByRole('button', {
                name: 'メニューを開く',
            });

            await user.click(menuButton);
            await user.click(
                within(drawer()).getByRole('button', {
                    name: 'メニューを閉じる',
                }),
            );

            expect(menuButton).toHaveFocus();
        });

        it('Esc キーで閉じるとメニューボタンへフォーカスを戻す', async () => {
            const user = userEvent.setup();
            renderSidebar();
            const menuButton = screen.getByRole('button', {
                name: 'メニューを開く',
            });

            await user.click(menuButton);
            within(drawer())
                .getByRole('button', { name: 'メニューを閉じる' })
                .focus();
            await user.keyboard('{Escape}');

            expect(menuButton).toHaveFocus();
        });

        it('リンクで閉じるとメニューボタンへフォーカスを戻す', async () => {
            const user = userEvent.setup();
            renderSidebar();
            const menuButton = screen.getByRole('button', {
                name: 'メニューを開く',
            });

            await user.click(menuButton);
            await user.click(
                within(drawer()).getByRole('link', { name: /チャット/ }),
            );

            expect(menuButton).toHaveFocus();
        });
    });
});
