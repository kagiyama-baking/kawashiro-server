export interface GenerateConfig {
    readonly name: string;
    readonly display_name: string;
    readonly tts_enabled: boolean;
}

export interface GenerateRequest {
    readonly config_name: string;
    readonly user_prompt?: string;
}

export interface GenerateResult {
    readonly text: string;
    readonly audioBlob: Blob | null;
    readonly audioUrl: string | null;
}

export const USER_PROMPT_MAX_LENGTH = 4000;
