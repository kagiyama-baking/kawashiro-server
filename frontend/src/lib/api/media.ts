import { apiClient } from '@/lib/api-client';
import type { ConvertImageParams } from '@/types/media';

interface MediaResult {
    readonly blob: Blob;
    readonly filename: string;
}

function extractFilename(
    contentDisposition: string | null,
    fallback: string,
): string {
    if (!contentDisposition) return fallback;
    const match = contentDisposition.match(/filename="?([^";\s]+)"?/);
    return match ? match[1] : fallback;
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
