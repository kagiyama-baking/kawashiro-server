import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { login } from '@/lib/api/auth';

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

describe('auth API', () => {
    it('正しい認証情報でトークンを取得できる', async () => {
        const result = await login({
            email: 'test@example.com',
            password: 'correct-password',
        });

        expect(result.token).toBe('test-token-123');
        expect(result.user_id).toBe(1);
        expect(result.email).toBe('test@example.com');
    });

    it('不正な認証情報でエラーが返る', async () => {
        await expect(
            login({
                email: 'test@example.com',
                password: 'wrong-password',
            }),
        ).rejects.toThrow();
    });
});
