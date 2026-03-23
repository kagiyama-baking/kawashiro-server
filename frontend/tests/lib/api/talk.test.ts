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

const server = setupServer(
    http.get('*/api/talk/configs/', () => {
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
    http.post('*/api/talk/synthesize/', () => {
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
        expect(result.text).toBe('おはようございます');
        expect(result.audioBlob).toBeInstanceOf(Blob);
        expect(result.audioBlob!.size).toBe('fake-audio-data'.length);
    });
});
