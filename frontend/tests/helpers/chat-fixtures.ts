import { HTTPError, type NormalizedOptions } from 'ky';
import type {
    ChatSessionDetail,
    ChatSessionListItem,
    ChatSessionMessage,
} from '@/types/talk';

export const NOW = '2026-11-02T09:30:00+09:00';

export function userMessage(
    overrides: Partial<ChatSessionMessage> = {},
): ChatSessionMessage {
    return {
        id: 1,
        sequence: 0,
        role: 'user',
        content: 'おはよう',
        audio_url: null,
        audio_format: '',
        audio_size_bytes: 0,
        created_at: NOW,
        ...overrides,
    };
}

export function assistantMessage(
    overrides: Partial<ChatSessionMessage> = {},
): ChatSessionMessage {
    return userMessage({
        id: 2,
        sequence: 1,
        role: 'assistant',
        content: 'おはようございます',
        ...overrides,
    });
}

export function sessionDetail(
    messages: readonly ChatSessionMessage[] = [],
    overrides: Partial<ChatSessionDetail> = {},
): ChatSessionDetail {
    return {
        id: 's1',
        title: '朝の挨拶',
        config_name: 'friendly',
        message_count: messages.length,
        total_audio_bytes: 0,
        created_at: NOW,
        updated_at: NOW,
        messages,
        ...overrides,
    };
}

export function sessionItem(
    overrides: Partial<ChatSessionListItem> = {},
): ChatSessionListItem {
    return {
        id: 's1',
        title: '朝の挨拶',
        config_name: 'friendly',
        message_count: 0,
        total_audio_bytes: 0,
        created_at: NOW,
        updated_at: NOW,
        ...overrides,
    };
}

export function httpError(body: unknown, status: number): HTTPError {
    return new HTTPError(
        new Response(body === null ? null : JSON.stringify(body), { status }),
        new Request('http://localhost/api/x'),
        {} as NormalizedOptions,
    );
}

export interface Deferred<T> {
    readonly promise: Promise<T>;
    readonly resolve: (value: T) => void;
    readonly reject: (reason: unknown) => void;
}

export function deferred<T>(): Deferred<T> {
    let resolve!: (value: T) => void;
    let reject!: (reason: unknown) => void;
    const promise = new Promise<T>((res, rej) => {
        resolve = res;
        reject = rej;
    });
    return { promise, resolve, reject };
}
