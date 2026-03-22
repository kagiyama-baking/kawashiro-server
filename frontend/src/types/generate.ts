export interface GenerateConfig {
    readonly name: string;
    readonly display_name: string;
    readonly tts_enabled: boolean;
    readonly use_weather: boolean;
    readonly use_events: boolean;
    readonly use_datetime: boolean;
}

export interface GenerateRequest {
    readonly config_name: string;
    readonly user_prompt: string;
}

export interface GenerateResult {
    readonly text: string;
    readonly audioBlob: Blob | null;
    readonly audioUrl: string | null;
}
