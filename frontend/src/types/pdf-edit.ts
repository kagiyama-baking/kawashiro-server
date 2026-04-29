/**
 * PDF編集機能の型定義
 *
 * クライアント完結型のページ編集（並び替え/削除/分割/トリミング）。
 * 元PDFは ArrayBuffer で保持し、編集状態はページ配列の最終形として
 * 表現する（操作キューではなくスナップショット方式）。
 */

/**
 * トリミング矩形（0〜1 の相対座標）。
 * 元ページサイズに対する割合で持つことで、ズーム倍率に依存しない。
 */
export interface CropRect {
    readonly x: number;
    readonly y: number;
    readonly width: number;
    readonly height: number;
}

/**
 * 編集後の論理ページ1枚を表す状態。
 *
 * - `id`         : UI 上のキー（並び替え/選択で使用）。一意な文字列。
 * - `sourceIndex`: 元PDFの 0-indexed ページ番号。
 * - `splitHalf`  : 左右分割時の半身。`null` は分割なし。
 * - `crop`       : トリミング矩形。`null` はトリミングなし。
 *
 * 分割（splitHalf != null）と トリミング（crop != null）は併用可能。
 * 出力時は、元ページの CropBox を `splitHalf` で半分にしてから
 * さらに `crop` で内側を切り出す形に合成する。
 */
export interface PageState {
    readonly id: string;
    readonly sourceIndex: number;
    readonly splitHalf: 'left' | 'right' | null;
    readonly crop: CropRect | null;
}

/**
 * サムネイル情報（元PDFのページ単位、splitやcropは未適用）。
 */
export interface SourcePageInfo {
    readonly sourceIndex: number;
    readonly width: number;
    readonly height: number;
    readonly thumbnailUrl: string;
}
