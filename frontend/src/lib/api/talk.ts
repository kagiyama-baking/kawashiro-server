import { apiClient } from '@/lib/api-client';
import type {
    GenerateConfig,
    GenerateRequest,
    GenerateResult,
} from '@/types/talk';

interface ConfigsResponse {
    readonly configs: GenerateConfig[];
}

export async function fetchConfigs(): Promise<GenerateConfig[]> {
    const response = await apiClient
        .get('talk/configs/')
        .json<ConfigsResponse>();
    return response.configs;
}

interface GenerateResponse {
    readonly greeting_text: string;
    readonly audio_data?: string | null;
    readonly audio_format?: string | null;
}

export async function generateText(
    request: GenerateRequest,
): Promise<GenerateResult> {
    const data = await apiClient
        .post('talk/synthesize/', {
            json: request,
            timeout: 120000,
        })
        .json<GenerateResponse>();

    const text = data.greeting_text;

    if (data.audio_data) {
        const binaryStr = atob(data.audio_data);
        const bytes = new Uint8Array(binaryStr.length);
        for (let i = 0; i < binaryStr.length; i++) {
            bytes[i] = binaryStr.charCodeAt(i);
        }
        const mimeMap: Record<string, string> = {
            wav: 'audio/wav',
            mp3: 'audio/mpeg',
            ogg: 'audio/ogg',
        };
        const mime = mimeMap[data.audio_format ?? 'wav'] ?? 'audio/wav';
        const audioBlob = new Blob([bytes], { type: mime });
        const audioUrl = URL.createObjectURL(audioBlob);
        return { text, audioBlob, audioUrl };
    }

    return { text, audioBlob: null, audioUrl: null };
}
