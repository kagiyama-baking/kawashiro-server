import { HTTPError } from 'ky';
import { apiClient } from '@/lib/api-client';
import type { ConvertImageParams } from '@/types/media';

interface MediaResult {
    readonly blob: Blob;
    readonly filename: string;
}

export async function extractApiErrorMessage(
    error: unknown,
    fallback: string,
): Promise<string> {
    if (!(error instanceof HTTPError)) return fallback;
    try {
        const body = (await error.response.json()) as unknown;
        if (
            body !== null &&
            typeof body === 'object' &&
            'error' in body &&
            typeof (body as { error: unknown }).error === 'string'
        ) {
            const message = (body as { error: string }).error.trim();
            if (message !== '') return message;
        }
    } catch {
        // JSON でないレスポンスや response body を二重消費した場合は fallback
    }
    return fallback;
}

function sanitizeDownloadFilename(name: string): string {
    // 改行・パス区切り・制御文字を除去（不正サーバー / MITM の改ざん対策の2段防御）
    // eslint-disable-next-line no-control-regex -- 制御文字の除去自体が目的
    return name.replace(/[\r\n\\/\x00-\x1f\x7f]/g, '_');
}

function extractFilename(
    contentDisposition: string | null,
    fallback: string,
): string {
    if (!contentDisposition) return fallback;
    // RFC 5987: filename*=UTF-8''<percent-encoded> を ASCII フォールバックより優先
    const utf8Match = contentDisposition.match(
        /filename\*\s*=\s*UTF-8''([^;]+)/i,
    );
    if (utf8Match) {
        try {
            return sanitizeDownloadFilename(
                decodeURIComponent(utf8Match[1].trim()),
            );
        } catch {
            // 不正なパーセントエンコードの場合は ASCII フォールバックへ
        }
    }
    const match = contentDisposition.match(/filename="?([^";\s]+)"?/);
    return match ? sanitizeDownloadFilename(match[1]) : fallback;
}

export async function convertImage(
    params: ConvertImageParams,
): Promise<MediaResult> {
    const formData = new FormData();
    formData.append('file', params.file);
    formData.append('output_format', params.output_format);
    if (params.quality !== undefined) {
        formData.append('quality', String(params.quality));
    }

    const response = await apiClient.post('media/convert-image/', {
        body: formData,
    });

    const blob = await response.blob();
    const filename = extractFilename(
        response.headers.get('Content-Disposition'),
        `converted.${params.output_format}`,
    );

    return { blob, filename };
}

export async function zipToPdf(file: File): Promise<MediaResult> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await apiClient.post('media/zip-to-pdf/', {
        body: formData,
    });

    const blob = await response.blob();
    const filename = extractFilename(
        response.headers.get('Content-Disposition'),
        'converted.pdf',
    );

    return { blob, filename };
}
