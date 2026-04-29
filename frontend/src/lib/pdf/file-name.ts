/**
 * 元PDFファイル名から編集後ファイル名を生成。
 *
 * - 拡張子 `.pdf` の前に `.edited` を挿入する（`book.pdf` → `book.edited.pdf`）
 * - 拡張子なしや非PDF拡張子の場合は末尾に `.edited.pdf` を付与
 * - 元ファイル名がnull/空のときは `edited.pdf` を返す
 *
 * セキュリティ: バックエンドの `build_pdf_filename`（`django_api/features/media/views.py`）
 * と対称になるよう、制御文字・改行・引用符・パス区切りをサニタイズする。`<a download>`
 * 属性経由ではブラウザが追加のサニタイズを行うが、サーバ側との対称性とOSファイル名の
 * 安全性のために自前で除去しておく。
 */
export function makeEditedFileName(original: string | null): string {
    const fallback = 'edited.pdf';
    if (!original) return fallback;
    const sanitized = sanitize(original);
    if (!sanitized) return fallback;
    const lower = sanitized.toLowerCase();
    if (lower.endsWith('.pdf')) {
        return `${sanitized.slice(0, -4)}.edited.pdf`;
    }
    return `${sanitized}.edited.pdf`;
}

function sanitize(name: string): string {
    return (
        name
            // パス区切りを除去（パストラバーサル対策）
            .replace(/[\\/]/g, '')
            // 制御文字 (NUL〜US, DEL)・改行・ダブルクォート
            // eslint-disable-next-line no-control-regex
            .replace(/[\r\n"\x00-\x1f\x7f]/g, '')
            .trim()
    );
}
