// iOS Safari の autoplay policy 回避用の極短サイレント WAV (mono, 16kHz, 1 sample)。
// ユーザー操作起点で先にこれを play() しておくと、同じ HTMLAudioElement の
// src を後で差し替えても再生できる。
export const SILENT_WAV_DATA_URL =
    'data:audio/wav;base64,UklGRiYAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQIAAAAAAA==';
