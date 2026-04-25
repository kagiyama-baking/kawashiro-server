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

export type ChatRole = 'user' | 'assistant';

export interface ChatMessageRequest {
    readonly role: ChatRole;
    readonly content: string;
}

export interface ChatRequest {
    readonly config_name: string;
    readonly messages: readonly ChatMessageRequest[];
}

export interface ChatMessageResult {
    readonly id: string;
    readonly role: ChatRole;
    readonly content: string;
    readonly audioBlob: Blob | null;
    readonly audioUrl: string | null;
    readonly audioFormat: string | null;
    readonly errorMessage: string | null;
}

export interface ChatResponse {
    readonly content: string;
    readonly audioBlob: Blob | null;
    readonly audioUrl: string | null;
    readonly audioFormat: string | null;
}

export const CHAT_MESSAGE_MAX_LENGTH = 4000;
export const CHAT_HISTORY_MAX_COUNT = 50;
