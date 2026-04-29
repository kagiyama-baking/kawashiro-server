/**
 * pdf-render.ts のテスト
 *
 * pdfjs-dist は完全モック化する。
 * - getDocument が呼ばれて PDF が読み込まれること
 * - エラー時に意味のあるメッセージで例外を投げること
 * - renderPageThumbnail が canvas → Blob を返すこと
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('pdfjs-dist', () => ({
    GlobalWorkerOptions: { workerSrc: '' },
    getDocument: vi.fn(),
}));

import * as pdfjsLib from 'pdfjs-dist';
import {
    EncryptedPdfError,
    InvalidPdfError,
    getOriginalPageSize,
    loadPdfDocument,
    renderPageThumbnail,
} from '@/lib/pdf/pdf-render';

interface MockPage {
    getViewport: ReturnType<typeof vi.fn>;
    render: ReturnType<typeof vi.fn>;
    cleanup: ReturnType<typeof vi.fn>;
}

interface MockPdf {
    numPages: number;
    getPage: ReturnType<typeof vi.fn>;
}

function createMockPage(width = 600, height = 800): MockPage {
    return {
        getViewport: vi.fn(({ scale = 1 }: { scale?: number } = {}) => ({
            width: width * scale,
            height: height * scale,
        })),
        render: vi.fn(() => ({ promise: Promise.resolve() })),
        cleanup: vi.fn(),
    };
}

function createMockPdf(numPages = 1, page?: MockPage): MockPdf {
    return {
        numPages,
        getPage: vi.fn(() => Promise.resolve(page ?? createMockPage())),
    };
}

describe('loadPdfDocument', () => {
    beforeEach(() => {
        vi.mocked(pdfjsLib.getDocument).mockReset();
    });

    it('PDFを読み込んでページ数を返す', async () => {
        const mockPdf = createMockPdf(5);
        vi.mocked(pdfjsLib.getDocument).mockReturnValue({
            promise: Promise.resolve(mockPdf),
        } as never);

        const buf = new ArrayBuffer(8);
        const result = await loadPdfDocument(buf);

        expect(result.numPages).toBe(5);
        expect(result.pdf).toBe(mockPdf);
    });

    it('入力バイト列を複製してから pdfjs に渡す（呼び出し元バッファとの共有を避ける）', async () => {
        const mockPdf = createMockPdf(1);
        vi.mocked(pdfjsLib.getDocument).mockReturnValue({
            promise: Promise.resolve(mockPdf),
        } as never);

        const original = new ArrayBuffer(4);
        new Uint8Array(original).set([1, 2, 3, 4]);
        await loadPdfDocument(original);

        const arg = vi.mocked(pdfjsLib.getDocument).mock.calls[0][0] as {
            data: Uint8Array;
        };
        expect(arg.data).toBeInstanceOf(Uint8Array);
        // 別のArrayBufferを指していること
        expect(arg.data.buffer).not.toBe(original);
        expect(Array.from(arg.data)).toEqual([1, 2, 3, 4]);
    });

    it('暗号化PDF（PasswordException）はEncryptedPdfErrorに変換する', async () => {
        // pdfjs の PasswordException を模倣（name='PasswordException'）
        const passwordError = Object.assign(new Error('Password required'), {
            name: 'PasswordException',
        });
        vi.mocked(pdfjsLib.getDocument).mockReturnValue({
            promise: Promise.reject(passwordError),
        } as never);

        await expect(loadPdfDocument(new ArrayBuffer(8))).rejects.toBeInstanceOf(
            EncryptedPdfError,
        );
    });

    it('破損PDF（InvalidPDFException）はInvalidPdfErrorに変換する', async () => {
        const invalidError = Object.assign(new Error('Invalid PDF'), {
            name: 'InvalidPDFException',
        });
        vi.mocked(pdfjsLib.getDocument).mockReturnValue({
            promise: Promise.reject(invalidError),
        } as never);

        await expect(loadPdfDocument(new ArrayBuffer(8))).rejects.toBeInstanceOf(
            InvalidPdfError,
        );
    });

    it('未知の例外はそのまま再送出する', async () => {
        const unknown = new Error('boom');
        vi.mocked(pdfjsLib.getDocument).mockReturnValue({
            promise: Promise.reject(unknown),
        } as never);

        await expect(loadPdfDocument(new ArrayBuffer(8))).rejects.toThrow(
            'boom',
        );
    });
});

describe('renderPageThumbnail', () => {
    beforeEach(() => {
        // canvas.toBlob を jsdom 用に常に呼べる形でモック
        HTMLCanvasElement.prototype.toBlob = function (
            cb: BlobCallback,
            type?: string,
        ) {
            cb(new Blob(['x'], { type: type ?? 'image/jpeg' }));
        };
        // jsdom は getContext('2d') が null を返すため簡易モック
        HTMLCanvasElement.prototype.getContext = vi.fn(
            () => ({}) as unknown,
        ) as unknown as HTMLCanvasElement['getContext'];
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it('指定ページをレンダリングしてBlob+寸法を返す', async () => {
        const page = createMockPage(600, 800);
        const pdf = createMockPdf(3, page) as unknown as Parameters<
            typeof renderPageThumbnail
        >[0];

        const result = await renderPageThumbnail(pdf, 1, 0.5);

        expect(result.blob).toBeInstanceOf(Blob);
        expect(result.width).toBe(300); // 600 * 0.5
        expect(result.height).toBe(400);
        // pdfjs は 1-indexed なので、pageIndex=1 → getPage(2)
        expect((pdf as unknown as MockPdf).getPage).toHaveBeenCalledWith(2);
        expect(page.cleanup).toHaveBeenCalled();
    });

    it('canvas.toBlob が null を返したら例外を投げる', async () => {
        HTMLCanvasElement.prototype.toBlob = function (cb: BlobCallback) {
            cb(null);
        };
        const pdf = createMockPdf(1) as unknown as Parameters<
            typeof renderPageThumbnail
        >[0];

        await expect(renderPageThumbnail(pdf, 0)).rejects.toThrow(
            /サムネイル/,
        );
    });
});

describe('getOriginalPageSize', () => {
    it('スケール1 のviewportサイズを返す', async () => {
        const page = createMockPage(595, 842); // A4 pt
        const pdf = createMockPdf(1, page) as unknown as Parameters<
            typeof getOriginalPageSize
        >[0];

        const size = await getOriginalPageSize(pdf, 0);

        expect(size).toEqual({ width: 595, height: 842 });
        expect(page.getViewport).toHaveBeenCalledWith({ scale: 1 });
    });
});
