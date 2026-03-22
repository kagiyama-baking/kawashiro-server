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
import { fetchModels, fetchStyles, synthesize } from '@/lib/api/tts';
import type { TtsParams } from '@/types/tts';

const server = setupServer(
    http.get('*/api/tts/models/', () => {
        return HttpResponse.json({ models: ['model-a', 'model-b'] });
    }),
    http.get('*/api/tts/models/:modelName/styles/', ({ params }) => {
        if (params.modelName === 'model-a') {
            return HttpResponse.json({
                styles: ['Neutral', 'Happy', 'Sad'],
            });
        }
        return HttpResponse.json({ styles: [] });
    }),
    http.post('*/api/tts/synthesize/', () => {
        const audioData = new Uint8Array([0x52, 0x49, 0x46, 0x46]);
        return new HttpResponse(audioData, {
            headers: {
                'Content-Type': 'audio/wav',
                'Content-Disposition': 'attachment; filename="tts_output.wav"',
            },
        });
    }),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('TTS API', () => {
    it('モデル一覧を取得できる', async () => {
        const models = await fetchModels();
        expect(models).toEqual(['model-a', 'model-b']);
    });

    it('指定モデルのスタイル一覧を取得できる', async () => {
        const styles = await fetchStyles('model-a');
        expect(styles).toEqual(['Neutral', 'Happy', 'Sad']);
    });

    it('音声合成でBlobが返る', async () => {
        const params: TtsParams = {
            text: 'こんにちは',
            style: 'Neutral',
            style_weight: 1.0,
            speed: 1.0,
            sdp_ratio: 0.2,
            noise_scale: 0.6,
            noise_scale_w: 0.8,
            format: 'wav',
        };

        const blob = await synthesize(params);
        expect(blob.size).toBeGreaterThan(0);
        expect(typeof blob.arrayBuffer).toBe('function');
    });
});
