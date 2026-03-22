import { create } from 'zustand';
import { DEFAULT_TTS_PARAMS, type TtsParams } from '@/types/tts';

type TtsParamsWithoutText = Omit<TtsParams, 'text'>;

interface TtsStore {
    readonly params: TtsParamsWithoutText;
    readonly setParam: <K extends keyof TtsParamsWithoutText>(
        key: K,
        value: TtsParamsWithoutText[K],
    ) => void;
    readonly resetParams: () => void;
}

export const useTtsStore = create<TtsStore>((set) => ({
    params: { ...DEFAULT_TTS_PARAMS },

    setParam: (key, value) => {
        set((state) => ({
            params: { ...state.params, [key]: value },
        }));
    },

    resetParams: () => {
        set({ params: { ...DEFAULT_TTS_PARAMS } });
    },
}));
