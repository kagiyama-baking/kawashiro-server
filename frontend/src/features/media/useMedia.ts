import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
    convertImage,
    extractApiErrorMessage,
    zipToPdf,
} from '@/lib/api/media';
import type { OutputFormat } from '@/types/media';

interface MediaResult {
    readonly blob: Blob;
    readonly filename: string;
    readonly url: string;
}

export function useMedia() {
    const [result, setResult] = useState<MediaResult | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const previousUrlRef = useRef<string | null>(null);

    const handleConvertImage = useCallback(
        async (file: File, outputFormat: OutputFormat, quality: number) => {
            setIsLoading(true);
            setError(null);

            if (previousUrlRef.current) {
                URL.revokeObjectURL(previousUrlRef.current);
            }
            setResult(null);

            try {
                const res = await convertImage({
                    file,
                    output_format: outputFormat,
                    quality,
                });
                const url = URL.createObjectURL(res.blob);
                previousUrlRef.current = url;
                setResult({ blob: res.blob, filename: res.filename, url });
                toast.success('画像を変換しました');
            } catch (e) {
                const msg = await extractApiErrorMessage(
                    e,
                    '画像変換に失敗しました',
                );
                setError(msg);
                toast.error(msg);
            } finally {
                setIsLoading(false);
            }
        },
        [],
    );

    const handleZipToPdf = useCallback(async (file: File) => {
        setIsLoading(true);
        setError(null);

        if (previousUrlRef.current) {
            URL.revokeObjectURL(previousUrlRef.current);
        }
        setResult(null);

        try {
            const res = await zipToPdf(file);
            const url = URL.createObjectURL(res.blob);
            previousUrlRef.current = url;
            setResult({ blob: res.blob, filename: res.filename, url });
            toast.success('PDFに変換しました');
        } catch (e) {
            const msg = await extractApiErrorMessage(
                e,
                'ZIP→PDF変換に失敗しました',
            );
            setError(msg);
            toast.error(msg);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        return () => {
            if (previousUrlRef.current) {
                URL.revokeObjectURL(previousUrlRef.current);
            }
        };
    }, []);

    const downloadResult = useCallback(() => {
        if (!result) return;
        const a = document.createElement('a');
        a.href = result.url;
        a.download = result.filename;
        a.click();
    }, [result]);

    return {
        result,
        isLoading,
        error,
        handleConvertImage,
        handleZipToPdf,
        downloadResult,
    } as const;
}
