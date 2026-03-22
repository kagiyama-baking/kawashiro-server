import { apiClient } from '@/lib/api-client';
import type {
    GenerateConfig,
    GenerateRequest,
    GenerateResult,
} from '@/types/generate';

/**
 * HTTPヘッダーのテキストをデコードする
 * Django が sanitize_for_header で制御文字を除去した後のテキスト、
 * または MIME エンコード（=?utf-8?b?...?=）をデコードする
 */
function decodeHeaderText(value: string): string {
    if (!value) return '';

    // MIME Base64 エンコード（=?utf-8?b?...?=）の場合
    const mimeMatch = value.match(/=\?([^?]+)\?([bBqQ])\?([^?]+)\?=/);
    if (mimeMatch) {
        const encoding = mimeMatch[2].toLowerCase();
        const encoded = mimeMatch[3];

        if (encoding === 'b') {
            try {
                const binary = atob(encoded);
                const bytes = new Uint8Array(binary.length);
                for (let i = 0; i < binary.length; i++) {
                    bytes[i] = binary.charCodeAt(i);
                }
                return new TextDecoder('utf-8').decode(bytes);
            } catch {
                return value;
            }
        }
    }

    // URL エンコードの場合
    try {
        return decodeURIComponent(value);
    } catch {
        return value;
    }
}

interface ConfigsResponse {
    readonly configs: GenerateConfig[];
}

export async function fetchConfigs(): Promise<GenerateConfig[]> {
    const response = await apiClient
        .get('generate/configs/')
        .json<ConfigsResponse>();
    return response.configs;
}

export async function generateText(
    request: GenerateRequest,
): Promise<GenerateResult> {
    const response = await apiClient.post('generate/generate/', {
        json: request,
        timeout: 120000,
    });

    const contentType = response.headers.get('Content-Type') ?? '';
    const rawText = response.headers.get('X-Generate-Text') ?? '';
    const text = decodeHeaderText(rawText);

    if (contentType.startsWith('audio/')) {
        const audioBlob = await response.blob();
        const audioUrl = URL.createObjectURL(audioBlob);
        return { text, audioBlob, audioUrl };
    }

    const data = (await response.json()) as { greeting_text: string };
    return { text: data.greeting_text, audioBlob: null, audioUrl: null };
}
