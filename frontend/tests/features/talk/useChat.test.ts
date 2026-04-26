import { act, renderHook, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { useChat } from '@/features/talk/useChat';

let abortHits = 0;

const server = setupServer(
    http.get('*/api/talk/configs/', () =>
        HttpResponse.json({
            configs: [
                { name: 'morning', display_name: '朝', tts_enabled: false },
            ],
        }),
    ),
    http.post('*/api/talk/chat/', async ({ request }) => {
        // request.signal で abort 検知
        await new Promise((resolve, reject) => {
            const t = setTimeout(resolve, 1000);
            request.signal.addEventListener('abort', () => {
                clearTimeout(t);
                abortHits += 1;
                reject(new DOMException('aborted', 'AbortError'));
            });
        });
        return HttpResponse.json({
            message: { role: 'assistant', content: '遅延応答' },
        });
    }),
);

beforeAll(() => server.listen());
afterEach(() => {
    server.resetHandlers();
    abortHits = 0;
});
afterAll(() => server.close());

describe('useChat - cancelMessage', () => {
    it('cancelMessage で fetch が abort され、ユーザーメッセージは残る', async () => {
        const { result } = renderHook(() => useChat());

        // configs ロード待ち
        await waitFor(() => expect(result.current.configs.length).toBe(1));

        act(() => {
            result.current.setInput('テスト送信');
        });

        // sendMessage を起動（待たない）
        let sendPromise!: Promise<void>;
        act(() => {
            sendPromise = result.current.sendMessage();
        });

        // ローディング状態とユーザーメッセージ追加を待つ
        await waitFor(() => {
            expect(result.current.isLoading).toBe(true);
            expect(result.current.messages.length).toBe(1);
        });
        expect(result.current.messages[0].role).toBe('user');
        expect(result.current.messages[0].content).toBe('テスト送信');

        // キャンセル
        act(() => {
            result.current.cancelMessage();
        });

        await act(async () => {
            await sendPromise;
        });

        // 検証: ローディング解除、abort 検知、ユーザーメッセージ保持、errorMessage に「キャンセルしました」
        expect(result.current.isLoading).toBe(false);
        expect(abortHits).toBeGreaterThanOrEqual(1);
        expect(result.current.messages.length).toBe(1);
        expect(result.current.messages[0].role).toBe('user');
        expect(result.current.messages[0].errorMessage).toBe(
            'キャンセルしました',
        );
        // グローバル error は設定しない
        expect(result.current.error).toBeNull();
    });
});
