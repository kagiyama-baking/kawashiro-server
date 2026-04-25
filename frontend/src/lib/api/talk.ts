import { apiClient } from '@/lib/api-client';
import type { ChatRequest, ChatResponse, GenerateConfig } from '@/types/talk';

interface ConfigsResponse {
    readonly configs: GenerateConfig[];
}

export async function fetchConfigs(): Promise<GenerateConfig[]> {
    const response = await apiClient
        .get('talk/configs/')
        .json<ConfigsResponse>();
    return response.configs;
}

const MIME_BY_FORMAT: Record<string, string> = {
    wav: 'audio/wav',
    mp3: 'audio/mpeg',
    ogg: 'audio/ogg',
};

interface AudioPayload {
    readonly audioBlob: Blob;
    readonly audioUrl: string;
    readonly audioFormat: string;
}

function decodeAudioPayload(
    base64: string,
    format: string | null | undefined,
): AudioPayload {
    const binaryStr = atob(base64);
    const bytes = new Uint8Array(binaryStr.length);
    for (let i = 0; i < binaryStr.length; i++) {
        bytes[i] = binaryStr.charCodeAt(i);
    }
    const fmt = format ?? 'wav';
    const mime = MIME_BY_FORMAT[fmt] ?? 'audio/wav';
    const audioBlob = new Blob([bytes], { type: mime });
    const audioUrl = URL.createObjectURL(audioBlob);
    return { audioBlob, audioUrl, audioFormat: fmt };
}

interface ChatRawResponse {
    readonly message: { readonly role: 'assistant'; readonly content: string };
    readonly audio_data?: string | null;
    readonly audio_format?: string | null;
}

export async function sendChat(request: ChatRequest): Promise<ChatResponse> {
    const data = await apiClient
        .post('talk/chat/', {
            json: request,
            timeout: 120000,
        })
        .json<ChatRawResponse>();

    const content = data.message.content;

    if (data.audio_data) {
        const { audioBlob, audioUrl, audioFormat } = decodeAudioPayload(
            data.audio_data,
            data.audio_format,
        );
        return { content, audioBlob, audioUrl, audioFormat };
    }

    return { content, audioBlob: null, audioUrl: null, audioFormat: null };
}
