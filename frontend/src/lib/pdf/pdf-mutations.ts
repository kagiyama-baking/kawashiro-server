/**
 * 編集状態（PageState[]）を実PDFに適用して新しいPDFバイト列を返す。
 *
 * 設計方針:
 * - **MediaBox は変えず CropBox のみ書き換える**（元のページサイズ・座標系を保つ）
 * - 分割（splitHalf）も CropBox の左右半分指定で表現（ピクセル再エンコードなし）
 * - トリミング（crop）は 0〜1 の相対座標で受け取り、PDF座標系（左下原点）に変換して合成
 * - copyPages は同じソースインデックスを複数回コピー可能なので、split で1ページから2ページに展開しても安全
 */
import { PDFDocument } from 'pdf-lib';
import type { PageState } from '@/types/pdf-edit';

export class EmptyOutputError extends Error {
    constructor() {
        super('出力するページがありません');
        this.name = 'EmptyOutputError';
    }
}

export async function applyEditsAndExport(
    sourceBytes: ArrayBuffer,
    pages: readonly PageState[],
): Promise<Uint8Array> {
    if (pages.length === 0) {
        // 0ページPDFは多くのリーダで開けないため、呼び出し側で防ぐべき不正状態として扱う。
        throw new EmptyOutputError();
    }
    const sourceDoc = await PDFDocument.load(sourceBytes);
    const newDoc = await PDFDocument.create();

    for (const page of pages) {
        const [copied] = await newDoc.copyPages(sourceDoc, [page.sourceIndex]);

        // 元 MediaBox を基準に CropBox を計算する。
        // 既存の CropBox（OCR済PDFなどで設定済の場合あり）も考慮する選択肢はあるが、
        // 今回は元の MediaBox 全体を編集対象として扱う（要件「元の座標系を保つ」と整合）。
        const mediaBox = copied.getMediaBox();
        let { x: cropX, y: cropY, width: cropW, height: cropH } = mediaBox;

        // 1. split を適用（左右半分）
        if (page.splitHalf === 'left') {
            cropW = mediaBox.width / 2;
        } else if (page.splitHalf === 'right') {
            cropX = mediaBox.x + mediaBox.width / 2;
            cropW = mediaBox.width / 2;
        }

        // 2. crop を相対座標で適用
        // HTMLのcrop座標は左上原点、PDFは左下原点なのでY軸反転する。
        if (page.crop) {
            const innerX = cropX + cropW * page.crop.x;
            const innerW = cropW * page.crop.width;
            const innerH = cropH * page.crop.height;
            const innerY = cropY + cropH * (1 - page.crop.y - page.crop.height);
            cropX = innerX;
            cropY = innerY;
            cropW = innerW;
            cropH = innerH;
        }

        copied.setCropBox(cropX, cropY, cropW, cropH);
        newDoc.addPage(copied);
    }

    return await newDoc.save();
}
