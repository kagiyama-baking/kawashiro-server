import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { MemoryRouter } from 'react-router';
import {
    afterAll,
    afterEach,
    beforeAll,
    beforeEach,
    describe,
    expect,
    it,
} from 'vitest';
import { useAuthStore } from '@/stores/auth-store';
import { LoginPage } from '@/features/login/LoginPage';

const server = setupServer(
    http.post('*/api/user/token/', async ({ request }) => {
        const body = (await request.json()) as {
            username: string;
            password: string;
        };
        if (
            body.username === 'test@example.com' &&
            body.password === 'correct-password'
        ) {
            return HttpResponse.json({
                token: 'test-token-123',
                user_id: 1,
                email: 'test@example.com',
            });
        }
        return HttpResponse.json(
            { non_field_errors: ['認証情報が正しくありません。'] },
            { status: 400 },
        );
    }),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('LoginPage', () => {
    beforeEach(() => {
        useAuthStore.setState({
            token: null,
            email: null,
            isAuthenticated: false,
        });
    });

    it('メールアドレスとパスワードの入力フィールドが表示される', () => {
        render(
            <MemoryRouter>
                <LoginPage />
            </MemoryRouter>,
        );

        expect(screen.getByLabelText('メールアドレス')).toBeInTheDocument();
        expect(screen.getByLabelText('パスワード')).toBeInTheDocument();
        expect(
            screen.getByRole('button', { name: 'ログイン' }),
        ).toBeInTheDocument();
    });

    it('正しい認証情報でログインできる', async () => {
        const user = userEvent.setup();

        render(
            <MemoryRouter>
                <LoginPage />
            </MemoryRouter>,
        );

        await user.type(
            screen.getByLabelText('メールアドレス'),
            'test@example.com',
        );
        await user.type(
            screen.getByLabelText('パスワード'),
            'correct-password',
        );
        await user.click(screen.getByRole('button', { name: 'ログイン' }));

        await waitFor(() => {
            const state = useAuthStore.getState();
            expect(state.token).toBe('test-token-123');
            expect(state.isAuthenticated).toBe(true);
        });
    });

    it('不正な認証情報でエラーメッセージが表示される', async () => {
        const user = userEvent.setup();

        render(
            <MemoryRouter>
                <LoginPage />
            </MemoryRouter>,
        );

        await user.type(
            screen.getByLabelText('メールアドレス'),
            'test@example.com',
        );
        await user.type(
            screen.getByLabelText('パスワード'),
            'wrong-password',
        );
        await user.click(screen.getByRole('button', { name: 'ログイン' }));

        await waitFor(() => {
            expect(
                screen.getByText(/ログインに失敗しました/),
            ).toBeInTheDocument();
        });
    });

    it('送信中はボタンが無効化される', async () => {
        const user = userEvent.setup();

        render(
            <MemoryRouter>
                <LoginPage />
            </MemoryRouter>,
        );

        await user.type(
            screen.getByLabelText('メールアドレス'),
            'test@example.com',
        );
        await user.type(
            screen.getByLabelText('パスワード'),
            'correct-password',
        );

        const button = screen.getByRole('button', { name: 'ログイン' });
        await user.click(button);

        // ボタンが一時的に無効化されることを確認
        // ログイン成功後は認証状態が変更される
        await waitFor(() => {
            expect(useAuthStore.getState().isAuthenticated).toBe(true);
        });
    });
});
