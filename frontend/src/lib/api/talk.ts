import { apiClient } from '@/lib/api-client';
import { parseEventStream, type ServerSentEvent } from '@/lib/sse';
import type {
    ChatSessionDetail,
    ChatSessionListResponse,
    ChatStreamEvent,
    GenerateConfig,
} from '@/types/talk';

interface ConfigsResponse {
    readonly configs: GenerateConfig[];
}

/** セッションの API のパス。id は URL から来るので、パスの区切りとして解釈されないようにする。 */
function sessionPath(id: string): string {
    return `talk/sessions/${encodeURIComponent(id)}/`;
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

interface GetSessionOptions {
    readonly timeout?: number;
    readonly retry?: number;
}

export async function getSession(
    id: string,
    options: GetSessionOptions = {},
): Promise<ChatSessionDetail> {
    return apiClient.get(sessionPath(id), options).json<ChatSessionDetail>();
}

export async function updateSessionTitle(
    id: string,
    title: string,
): Promise<ChatSessionDetail> {
    return apiClient
        .patch(sessionPath(id), { json: { title } })
        .json<ChatSessionDetail>();
}

export async function deleteSession(id: string): Promise<void> {
    await apiClient.delete(sessionPath(id));
}

interface SendOptions {
    readonly signal?: AbortSignal;
}

// JSONRenderer のみの DRF は text/event-stream 単独の指定に 406 を返すので application/json も付ける
const STREAM_REQUEST_OPTIONS = {
    headers: { Accept: 'text/event-stream, application/json' },
    retry: 0,
    timeout: 120000,
} as const;

const STREAM_EVENT_TYPES: ReadonlySet<string> = new Set<
    ChatStreamEvent['type']
>([
    'start',
    'delta',
    'message',
    'audio',
    'audio_error',
    'title',
    'error',
    'done',
]);

/** 知らないイベントと解釈できない data は null にして読み飛ばす。 */
function toChatStreamEvent({
    event,
    data,
}: ServerSentEvent): ChatStreamEvent | null {
    if (!STREAM_EVENT_TYPES.has(event)) return null;
    try {
        const payload: unknown = JSON.parse(data);
        if (payload === null || typeof payload !== 'object') return null;
        return { ...payload, type: event } as ChatStreamEvent;
    } catch {
        return null;
    }
}

async function* readChatStream(
    response: Response,
): AsyncGenerator<ChatStreamEvent> {
    if (!response.body) return;
    for await (const raw of parseEventStream(response.body)) {
        const event = toChatStreamEvent(raw);
        if (event) yield event;
    }
}

/** メッセージを送信し、応答を逐次受け取る。事前検証の失敗は HTTPError で投げる。 */
export async function* streamMessage(
    sessionId: string,
    content: string,
    options: SendOptions = {},
): AsyncGenerator<ChatStreamEvent> {
    const response = await apiClient.post(
        `${sessionPath(sessionId)}messages/`,
        {
            ...STREAM_REQUEST_OPTIONS,
            json: { content },
            signal: options.signal,
        },
    );
    yield* readChatStream(response);
}

/** メッセージを編集して再送し、応答を逐次受け取る。対象以降の履歴は置き換わる。 */
export async function* streamEdit(
    sessionId: string,
    msgId: number,
    content: string,
    options: SendOptions = {},
): AsyncGenerator<ChatStreamEvent> {
    const response = await apiClient.patch(
        `${sessionPath(sessionId)}messages/${msgId}/`,
        {
            ...STREAM_REQUEST_OPTIONS,
            json: { content },
            signal: options.signal,
        },
    );
    yield* readChatStream(response);
}

export async function fetchAudioBlob(
    sessionId: string,
    msgId: number,
): Promise<Blob> {
    const response = await apiClient.get(
        `${sessionPath(sessionId)}audio/${msgId}/`,
    );
    return response.blob();
}

export async function deleteAudio(
    sessionId: string,
    msgId: number,
): Promise<void> {
    await apiClient.delete(`${sessionPath(sessionId)}audio/${msgId}/`);
}

export async function bulkDeleteAudio(sessionId: string): Promise<void> {
    await apiClient.delete(`${sessionPath(sessionId)}audio/`);
}
