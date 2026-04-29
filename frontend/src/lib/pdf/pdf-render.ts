/**
 * pdf.js を用いた PDF 読み込み・サムネイル生成の薄ラッパー。
 *
 * - 入力 ArrayBuffer は pdfjs に渡す前に複製（呼び出し元のバッファ共有を避ける）
 * - 暗号化PDF / 破損PDF を独自エラーで区別して呼び出し側で UI 表示を分岐させる
 * - サムネイルは `<canvas>` にレンダリングしてから JPEG Blob 化（メモリ効率優先）
 */
import * as pdfjsLib from 'pdfjs-dist';
import type { PDFDocumentProxy } from 'pdfjs-dist';

export class EncryptedPdfError extends Error {
    constructor() {
        super('暗号化されたPDFは編集できません');
        this.name = 'EncryptedPdfError';
    }
}

export class InvalidPdfError extends Error {
    constructor() {
        super('PDFファイルが破損しているか、形式が不正です');
        this.name = 'InvalidPdfError';
    }
}

export interface LoadResult {
    readonly pdf: PDFDocumentProxy;
    readonly numPages: number;
}

/**
 * ArrayBuffer から PDF を読み込む。
 *
 * pdfjs はバッファを内部で参照保持し、編集側で同じバッファを書き換えると
 * レンダリング結果が壊れるため、ここで複製してから渡す。
 */
export async function loadPdfDocument(data: ArrayBuffer): Promise<LoadResult> {
    const copy = new Uint8Array(data.byteLength);
    copy.set(new Uint8Array(data));

    try {
        const loadingTask = pdfjsLib.getDocument({ data: copy });
        const pdf = await loadingTask.promise;
        return { pdf, numPages: pdf.numPages };
    } catch (err) {
        if (err instanceof Error) {
            if (err.name === 'PasswordException') {
                throw new EncryptedPdfError();
            }
            if (err.name === 'InvalidPDFException') {
                throw new InvalidPdfError();
            }
        }
        throw err;
    }
}

/**
 * 指定ページをレンダリングして JPEG Blob を返す。
 *
 * @param pageIndex 0-indexed のページ番号（pdfjs内部では +1 する）
 * @param scale 元ページサイズに対する縮尺。サムネ用途なら 0.2〜0.3 推奨
 */
export async function renderPageThumbnail(
    pdf: PDFDocumentProxy,
    pageIndex: number,
    scale = 0.3,
): Promise<{ blob: Blob; width: number; height: number }> {
    const page = await pdf.getPage(pageIndex + 1);
    try {
        const viewport = page.getViewport({ scale });
        const canvas = document.createElement('canvas');
        canvas.width = Math.ceil(viewport.width);
        canvas.height = Math.ceil(viewport.height);

        const ctx = canvas.getContext('2d');
        if (!ctx) {
            throw new Error('Canvas 2D コンテキストを取得できませんでした');
        }

        // pdfjs 5.x は canvas + canvasContext 両指定可。互換性のため両方渡す。
        await page.render({
            canvasContext: ctx,
            viewport,
            canvas,
        } as unknown as Parameters<typeof page.render>[0]).promise;

        const blob = await new Promise<Blob | null>((resolve) =>
            canvas.toBlob(resolve, 'image/jpeg', 0.7),
        );
        if (!blob) {
            throw new Error('サムネイルの生成に失敗しました');
        }
        return { blob, width: viewport.width, height: viewport.height };
    } finally {
        page.cleanup();
    }
}

/**
 * 指定ページの実寸（PDFポイント単位）を返す。
 * トリミング座標を 0〜1 から絶対値へ復元する際の基準として使う。
 */
export async function getOriginalPageSize(
    pdf: PDFDocumentProxy,
    pageIndex: number,
): Promise<{ width: number; height: number }> {
    const page = await pdf.getPage(pageIndex + 1);
    try {
        const viewport = page.getViewport({ scale: 1 });
        return { width: viewport.width, height: viewport.height };
    } finally {
        page.cleanup();
    }
}
