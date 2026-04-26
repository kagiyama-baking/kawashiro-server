import { apiClient } from '@/lib/api-client';
import type {
    ChatSessionDetail,
    ChatSessionListResponse,
    GenerateConfig,
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

interface ListSessionsParams {
    readonly limit?: number;
    readonly offset?: number;
}

export async function listSessions(
    params: ListSessionsParams = {},
): Promise<ChatSessionListResponse> {
    const search: Record<string, string> = {};
    if (params.limit !== undefined) search.limit = String(params.limit);
    if (params.offset !== undefined) search.offset = String(params.offset);
    return apiClient
        .get('talk/sessions/', { searchParams: search })
        .json<ChatSessionListResponse>();
}

export async function createSession(
    configName: string,
): Promise<ChatSessionDetail> {
    return apiClient
        .post('talk/sessions/', { json: { config_name: configName } })
        .json<ChatSessionDetail>();
}

export async function getSession(id: string): Promise<ChatSessionDetail> {
    return apiClient.get(`talk/sessions/${id}/`).json<ChatSessionDetail>();
}

export async function updateSessionTitle(
    id: string,
    title: string,
): Promise<ChatSessionDetail> {
    return apiClient
        .patch(`talk/sessions/${id}/`, { json: { title } })
        .json<ChatSessionDetail>();
}

export async function deleteSession(id: string): Promise<void> {
    await apiClient.delete(`talk/sessions/${id}/`);
}

interface SendOptions {
    readonly signal?: AbortSignal;
}

export async function postMessage(
    sessionId: string,
    content: string,
    options: SendOptions = {},
): Promise<ChatSessionDetail> {
    return apiClient
        .post(`talk/sessions/${sessionId}/messages/`, {
            json: { content },
            timeout: 120000,
            signal: options.signal,
        })
        .json<ChatSessionDetail>();
}

export async function editMessage(
    sessionId: string,
    msgId: number,
    content: string,
    options: SendOptions = {},
): Promise<ChatSessionDetail> {
    return apiClient
        .patch(`talk/sessions/${sessionId}/messages/${msgId}/`, {
            json: { content },
            timeout: 120000,
            signal: options.signal,
        })
        .json<ChatSessionDetail>();
}

export async function fetchAudioBlob(
    sessionId: string,
    msgId: number,
): Promise<Blob> {
    const response = await apiClient.get(
        `talk/sessions/${sessionId}/audio/${msgId}/`,
    );
    return response.blob();
}

export async function deleteAudio(
    sessionId: string,
    msgId: number,
): Promise<void> {
    await apiClient.delete(`talk/sessions/${sessionId}/audio/${msgId}/`);
}

export async function bulkDeleteAudio(sessionId: string): Promise<void> {
    await apiClient.delete(`talk/sessions/${sessionId}/audio/`);
}
