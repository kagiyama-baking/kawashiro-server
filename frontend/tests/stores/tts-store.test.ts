import { beforeEach, describe, expect, it } from 'vitest';
import { useTtsStore } from '@/stores/tts-store';
import { DEFAULT_TTS_PARAMS } from '@/types/tts';

describe('tts-store', () => {
    beforeEach(() => {
        useTtsStore.getState().resetParams();
    });

    it('初期値がデフォルトパラメータと一致する', () => {
        const { params } = useTtsStore.getState();
        expect(params).toEqual(DEFAULT_TTS_PARAMS);
    });

    it('setParam で個別パラメータを変更できる', () => {
        useTtsStore.getState().setParam('speed', 1.5);
        expect(useTtsStore.getState().params.speed).toBe(1.5);
    });

    it('setParam で他のパラメータに影響しない', () => {
        useTtsStore.getState().setParam('speed', 1.5);
        expect(useTtsStore.getState().params.style).toBe('Neutral');
        expect(useTtsStore.getState().params.noise_scale).toBe(0.6);
    });

    it('resetParams でデフォルトに戻る', () => {
        useTtsStore.getState().setParam('speed', 2.0);
        useTtsStore.getState().setParam('style', 'Happy');
        useTtsStore.getState().resetParams();

        expect(useTtsStore.getState().params).toEqual(DEFAULT_TTS_PARAMS);
    });
});
