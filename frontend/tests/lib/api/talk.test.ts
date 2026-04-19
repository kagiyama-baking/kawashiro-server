import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import {
    afterAll,
    afterEach,
    beforeAll,
    describe,
    expect,
    it,
} from 'vitest';
import { fetchConfigs, generateText } from '@/lib/api/talk';

let lastSynthesizeBody: Record<string, unknown> | null = null;

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
    http.post('*/api/talk/synthesize/', async ({ request }) => {
        lastSynthesizeBody = (await request.json()) as Record<string, unknown>;
        // Base64エンコードされたfake audio data
        const audioData = btoa('fake-audio-data');
        return HttpResponse.json({
            greeting_text: 'おはようございます',
            audio_data: audioData,
            audio_format: 'wav',
        });
    }),
);

beforeAll(() => server.listen());
afterEach(() => {
    server.resetHandlers();
    lastSynthesizeBody = null;
});
afterAll(() => server.close());

describe('Generate API', () => {
    it('設定一覧を取得できる', async () => {
        const configs = await fetchConfigs();
        expect(configs).toHaveLength(1);
        expect(configs[0].name).toBe('morning');
        expect(configs[0].display_name).toBe('朝のあいさつ');
    });

    it('テキスト生成でレスポンスが返る', async () => {
        const result = await generateText({
            config_name: 'morning',
        });
        expect(result.text).toBe('おはようございます');
        expect(result.audioBlob).toBeInstanceOf(Blob);
        expect(result.audioBlob!.size).toBe('fake-audio-data'.length);
    });

    it('user_prompt 未指定時はリクエストに含まれない', async () => {
        await generateText({ config_name: 'morning' });
        expect(lastSynthesizeBody).toEqual({ config_name: 'morning' });
    });

    it('user_prompt 指定時はリクエストに含まれる', async () => {
        await generateText({
            config_name: 'morning',
            user_prompt: '今日は {{datetime}} です',
        });
        expect(lastSynthesizeBody).toEqual({
            config_name: 'morning',
            user_prompt: '今日は {{datetime}} です',
        });
    });
});
