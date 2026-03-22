export interface TtsParams {
    readonly text: string;
    readonly model?: string;
    readonly style: string;
    readonly style_weight: number;
    readonly speed: number;
    readonly sdp_ratio: number;
    readonly noise_scale: number;
    readonly noise_scale_w: number;
    readonly format: 'wav' | 'mp3' | 'ogg';
}

export const DEFAULT_TTS_PARAMS: Omit<TtsParams, 'text'> = {
    style: 'Neutral',
    style_weight: 1.0,
    speed: 1.2,
    sdp_ratio: 0.2,
    noise_scale: 0.6,
    noise_scale_w: 0.8,
    format: 'wav',
} as const;

export interface TtsParamConfig {
    readonly key: keyof Omit<TtsParams, 'text' | 'model' | 'style' | 'format'>;
    readonly label: string;
    readonly min: number;
    readonly max: number;
    readonly step: number;
}

export const TTS_PARAM_CONFIGS: readonly TtsParamConfig[] = [
    { key: 'speed', label: 'スピード', min: 0.5, max: 2.0, step: 0.1 },
    {
        key: 'style_weight',
        label: 'スタイル強度',
        min: 0.0,
        max: 10.0,
        step: 0.1,
    },
    { key: 'sdp_ratio', label: 'SDP比率', min: 0.0, max: 1.0, step: 0.05 },
    {
        key: 'noise_scale',
        label: 'ノイズスケール',
        min: 0.0,
        max: 1.0,
        step: 0.05,
    },
    {
        key: 'noise_scale_w',
        label: 'ノイズスケールW',
        min: 0.0,
        max: 1.0,
        step: 0.05,
    },
] as const;
