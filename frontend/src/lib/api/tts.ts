import { apiClient } from '@/lib/api-client';
import type { TtsParams } from '@/types/tts';

interface ModelsResponse {
    readonly models: string[];
}

interface StylesResponse {
    readonly styles: string[];
}

export async function fetchModels(): Promise<string[]> {
    const response = await apiClient.get('tts/models/').json<ModelsResponse>();
    return response.models;
}

export async function fetchStyles(modelName: string): Promise<string[]> {
    const response = await apiClient
        .get(`tts/models/${encodeURIComponent(modelName)}/styles/`)
        .json<StylesResponse>();
    return response.styles;
}

export async function synthesize(params: TtsParams): Promise<Blob> {
    return apiClient
        .post('tts/synthesize/', {
            json: params,
        })
        .blob();
}
