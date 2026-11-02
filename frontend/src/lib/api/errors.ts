import { HTTPError } from 'ky';

function nonEmptyText(value: unknown): string | null {
    if (typeof value !== 'string') return null;
    const text = value.trim();
    return text === '' ? null : text;
}

/**
 * API のエラー本文から表示する文言を取り出す。
 * 形は 3 通りある: `{"error": "..."}`、DRF の例外 `{"detail": "..."}`、DRF の項目エラー `{"content": ["..."]}`。
 */
function messageFromBody(body: unknown): string | null {
    if (body === null || typeof body !== 'object' || Array.isArray(body)) {
        return null;
    }
    const fields = body as Record<string, unknown>;
    const direct = nonEmptyText(fields.error) ?? nonEmptyText(fields.detail);
    if (direct !== null) return direct;

    for (const value of Object.values(fields)) {
        const text = Array.isArray(value) ? nonEmptyText(value[0]) : null;
        if (text !== null) return text;
    }
    return null;
}

export async function extractApiErrorMessage(
    error: unknown,
    fallback: string,
): Promise<string> {
    if (!(error instanceof HTTPError)) return fallback;
    try {
        const body = (await error.response.json()) as unknown;
        return messageFromBody(body) ?? fallback;
    } catch {
        // JSON でないレスポンスや response body を二重消費した場合は fallback
        return fallback;
    }
}
