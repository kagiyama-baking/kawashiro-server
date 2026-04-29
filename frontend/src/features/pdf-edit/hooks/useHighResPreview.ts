import { useEffect, useState } from 'react';
import {
    loadPdfDocument,
    renderPageThumbnail,
} from '@/lib/pdf/pdf-render';
import type { PDFDocumentProxy } from 'pdfjs-dist';

interface PreviewState {
    readonly status: 'loading' | 'ready' | 'error';
    readonly url: string | null;
    readonly errorMessage: string | null;
}

/**
 * トリミングダイアログ用の高解像度プレビューを生成する。
 *
 * - サムネイル（0.3倍）では細かい余白の調整が困難なため、
 *   ダイアログ表示時に元PDFを 2.0 倍で再レンダリングして
 *   ピクセル等倍に近いプレビューを表示する。
 * - 呼び出し側がアンマウントされるとObjectURLを必ず解放する。
 * - 引数は呼び出し側でガード済の前提（null は受け取らない）。
 */
export function useHighResPreview(
    sourceBytes: ArrayBuffer,
    sourceIndex: number,
): PreviewState {
    const [state, setState] = useState<PreviewState>({
        status: 'loading',
        url: null,
        errorMessage: null,
    });

    useEffect(() => {
        let cancelled = false;
        let createdUrl: string | null = null;
        let pdf: PDFDocumentProxy | null = null;

        const run = async () => {
            try {
                const loaded = await loadPdfDocument(sourceBytes);
                pdf = loaded.pdf;
                if (cancelled) return;
                const { blob } = await renderPageThumbnail(
                    pdf,
                    sourceIndex,
                    2.0,
                );
                if (cancelled) return;
                createdUrl = URL.createObjectURL(blob);
                setState({
                    status: 'ready',
                    url: createdUrl,
                    errorMessage: null,
                });
            } catch (e) {
                if (cancelled) return;
                setState({
                    status: 'error',
                    url: null,
                    errorMessage:
                        e instanceof Error
                            ? e.message
                            : 'プレビューの生成に失敗しました',
                });
            }
        };
        run();

        return () => {
            cancelled = true;
            // ObjectURL は <img src> から参照されている可能性があるため、
            // cleanup の同期実行で revoke すると Strict Mode の二重実行や
            // ダイアログ連続開閉時に画像が壊れて見える可能性がある。
            // 次フレームに遅延して、img のロード完了を確実に待つ。
            if (createdUrl) {
                const url = createdUrl;
                setTimeout(() => URL.revokeObjectURL(url), 0);
            }
            if (pdf) pdf.cleanup();
        };
    }, [sourceBytes, sourceIndex]);

    return state;
}
