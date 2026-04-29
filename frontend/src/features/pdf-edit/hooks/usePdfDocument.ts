import { useCallback, useEffect, useRef, useState } from 'react';
import {
    EncryptedPdfError,
    InvalidPdfError,
    loadPdfDocument,
    renderPageThumbnail,
} from '@/lib/pdf/pdf-render';
import type { SourcePageInfo } from '@/types/pdf-edit';
import type { PDFDocumentProxy } from 'pdfjs-dist';

interface UsePdfDocumentResult {
    readonly sourceBytes: ArrayBuffer | null;
    readonly sourceFileName: string | null;
    readonly sourcePages: readonly SourcePageInfo[];
    readonly isLoading: boolean;
    readonly progress: { current: number; total: number } | null;
    readonly error: string | null;
    readonly loadFile: (file: File) => Promise<void>;
    readonly reset: () => void;
}

/**
 * PDFファイルを読み込んで全ページのサムネイルを生成する。
 *
 * - サムネ生成は逐次実行（並列だと本番制約のないブラウザでもメモリ圧迫しやすい）
 * - 生成済みObjectURLはリセット/アンマウント時に必ずrevokeする
 */
export function usePdfDocument(): UsePdfDocumentResult {
    const [sourceBytes, setSourceBytes] = useState<ArrayBuffer | null>(null);
    const [sourceFileName, setSourceFileName] = useState<string | null>(null);
    const [sourcePages, setSourcePages] = useState<SourcePageInfo[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [progress, setProgress] = useState<{
        current: number;
        total: number;
    } | null>(null);
    const [error, setError] = useState<string | null>(null);

    // revoke用に蓄積。setSourcePagesと別に管理し、リセット時に確実に解放する。
    const objectUrlsRef = useRef<string[]>([]);

    const revokeAllUrls = useCallback(() => {
        for (const url of objectUrlsRef.current) {
            URL.revokeObjectURL(url);
        }
        objectUrlsRef.current = [];
    }, []);

    const reset = useCallback(() => {
        revokeAllUrls();
        setSourceBytes(null);
        setSourceFileName(null);
        setSourcePages([]);
        setProgress(null);
        setError(null);
    }, [revokeAllUrls]);

    const loadFile = useCallback(
        async (file: File) => {
            setIsLoading(true);
            setError(null);
            revokeAllUrls();
            setSourcePages([]);
            setSourceBytes(null);
            setProgress(null);

            let pdf: PDFDocumentProxy | null = null;
            try {
                const bytes = await file.arrayBuffer();
                const loaded = await loadPdfDocument(bytes);
                pdf = loaded.pdf;
                setSourceBytes(bytes);
                setSourceFileName(file.name);
                setProgress({ current: 0, total: loaded.numPages });

                const pages: SourcePageInfo[] = [];
                for (let i = 0; i < loaded.numPages; i++) {
                    const { blob, width, height } = await renderPageThumbnail(
                        pdf,
                        i,
                        0.3,
                    );
                    const url = URL.createObjectURL(blob);
                    objectUrlsRef.current.push(url);
                    pages.push({
                        sourceIndex: i,
                        width,
                        height,
                        thumbnailUrl: url,
                    });
                    setProgress({ current: i + 1, total: loaded.numPages });
                }
                setSourcePages(pages);
            } catch (e) {
                if (e instanceof EncryptedPdfError) {
                    setError('暗号化されたPDFは編集できません');
                } else if (e instanceof InvalidPdfError) {
                    setError('PDFファイルが破損しているか、形式が不正です');
                } else if (e instanceof Error) {
                    setError(`PDFの読み込みに失敗しました: ${e.message}`);
                } else {
                    setError('PDFの読み込みに失敗しました');
                }
                revokeAllUrls();
                setSourcePages([]);
                setSourceBytes(null);
                setSourceFileName(null);
            } finally {
                if (pdf) {
                    pdf.cleanup();
                }
                setIsLoading(false);
                setProgress(null);
            }
        },
        [revokeAllUrls],
    );

    useEffect(() => {
        return () => {
            revokeAllUrls();
        };
    }, [revokeAllUrls]);

    return {
        sourceBytes,
        sourceFileName,
        sourcePages,
        isLoading,
        progress,
        error,
        loadFile,
        reset,
    };
}
