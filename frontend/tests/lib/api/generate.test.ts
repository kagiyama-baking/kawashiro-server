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
import { fetchConfigs, generateText } from '@/lib/api/generate';

const server = setupServer(
    http.get('*/api/generate/configs/', () => {
        return HttpResponse.json({
            configs: [
                {
                    name: 'morning',
                    display_name: '朝のあいさつ',
                    tts_enabled: true,
                    use_weather: true,
                    use_events: true,
                    use_datetime: true,
                },
            ],
        });
    }),
    http.post('*/api/generate/generate/', () => {
        return new HttpResponse('fake-audio-data', {
            status: 200,
            headers: {
                'Content-Type': 'audio/wav',
                'X-Generate-Text': encodeURIComponent('おはようございます'),
            },
        });
    }),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
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
            user_prompt: 'テスト',
        });
        expect(result.text).toBe('\u304a\u306f\u3088\u3046\u3054\u3056\u3044\u307e\u3059');
        expect(result.audioBlob).not.toBeNull();
        expect(result.audioBlob!.size).toBeGreaterThan(0);
    });
});
