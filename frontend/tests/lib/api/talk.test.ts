import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { fetchConfigs, sendChat } from '@/lib/api/talk';

let lastChatBody: Record<string, unknown> | null = null;

const server = setupServer(
    http.get('*/api/talk/configs/', () => {
        return HttpResponse.json({
            configs: [
                {
                    name: 'morning',
                    display_name: '朝のあいさつ',
                    tts_enabled: true,
                },
            ],
        });
    }),
    http.post('*/api/talk/chat/', async ({ request }) => {
        lastChatBody = (await request.json()) as Record<string, unknown>;
        const audioData = btoa('fake-audio-data');
        return HttpResponse.json({
            message: { role: 'assistant', content: 'こんにちは' },
            audio_data: audioData,
            audio_format: 'wav',
        });
    }),
);

beforeAll(() => server.listen());
afterEach(() => {
    server.resetHandlers();
    lastChatBody = null;
});
afterAll(() => server.close());

describe('Talk API', () => {
    it('設定一覧を取得できる', async () => {
        const configs = await fetchConfigs();
        expect(configs).toHaveLength(1);
        expect(configs[0].name).toBe('morning');
        expect(configs[0].display_name).toBe('朝のあいさつ');
    });

    it('チャット送信でレスポンスが返る', async () => {
        const result = await sendChat({
            config_name: 'morning',
            messages: [{ role: 'user', content: 'おはよう' }],
        });
        expect(result.content).toBe('こんにちは');
        expect(result.audioBlob).toBeInstanceOf(Blob);
        expect(result.audioBlob!.size).toBe('fake-audio-data'.length);
        expect(result.audioFormat).toBe('wav');
    });

    it('messages 配列がそのままサーバへ送られる', async () => {
        const messages = [
            { role: 'user' as const, content: 'おはよう' },
            { role: 'assistant' as const, content: 'おはようございます' },
            { role: 'user' as const, content: '今日の予定は？' },
        ];
        await sendChat({ config_name: 'morning', messages });
        expect(lastChatBody).toEqual({
            config_name: 'morning',
            messages,
        });
    });

    it('AbortSignal で abort されたら reject される', async () => {
        server.use(
            http.post('*/api/talk/chat/', async () => {
                await new Promise((resolve) => setTimeout(resolve, 200));
                return HttpResponse.json({
                    message: { role: 'assistant', content: 'late' },
                });
            }),
        );

        const controller = new AbortController();
        const promise = sendChat(
            {
                config_name: 'morning',
                messages: [{ role: 'user', content: 'おはよう' }],
            },
            { signal: controller.signal },
        );
        controller.abort();

        await expect(promise).rejects.toMatchObject({ name: 'AbortError' });
    });

    it('音声なしレスポンスは audioBlob が null', async () => {
        server.use(
            http.post('*/api/talk/chat/', () => {
                return HttpResponse.json({
                    message: { role: 'assistant', content: '応答のみ' },
                });
            }),
        );
        const result = await sendChat({
            config_name: 'morning',
            messages: [{ role: 'user', content: 'test' }],
        });
        expect(result.content).toBe('応答のみ');
        expect(result.audioBlob).toBeNull();
        expect(result.audioUrl).toBeNull();
        expect(result.audioFormat).toBeNull();
    });
});
