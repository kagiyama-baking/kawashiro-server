import { describe, expect, it } from 'vitest';
import { makeEditedFileName } from '@/lib/pdf/file-name';

describe('makeEditedFileName', () => {
    it('null は edited.pdf にフォールバックする', () => {
        expect(makeEditedFileName(null)).toBe('edited.pdf');
    });

    it('空文字列も edited.pdf にフォールバックする', () => {
        expect(makeEditedFileName('')).toBe('edited.pdf');
    });

    it('.pdf 拡張子の前に .edited を挿入する', () => {
        expect(makeEditedFileName('book.pdf')).toBe('book.edited.pdf');
    });

    it('大文字の .PDF も拡張子として認識して挿入する', () => {
        expect(makeEditedFileName('SCAN.PDF')).toBe('SCAN.edited.pdf');
    });

    it('拡張子なしの場合は末尾に .edited.pdf を付与する', () => {
        expect(makeEditedFileName('document')).toBe('document.edited.pdf');
    });

    it('非PDF拡張子の場合は末尾にそのまま付与する', () => {
        expect(makeEditedFileName('photo.jpg')).toBe('photo.jpg.edited.pdf');
    });

    it('日本語ファイル名でも動作する', () => {
        expect(makeEditedFileName('書籍スキャン.pdf')).toBe(
            '書籍スキャン.edited.pdf',
        );
    });

    it('制御文字・改行を除去する', () => {
        expect(makeEditedFileName('foo\r\nbar.pdf')).toBe('foobar.edited.pdf');
        expect(makeEditedFileName('a\x00b\x1fc.pdf')).toBe('abc.edited.pdf');
    });

    it('ダブルクォートを除去する', () => {
        expect(makeEditedFileName('"my book".pdf')).toBe('my book.edited.pdf');
    });

    it('パス区切りを除去する（パストラバーサル対策）', () => {
        expect(makeEditedFileName('../etc/passwd.pdf')).toBe(
            '..etcpasswd.edited.pdf',
        );
        expect(makeEditedFileName('a/b\\c.pdf')).toBe('abc.edited.pdf');
    });

    it('サニタイズで空になる場合はフォールバック', () => {
        expect(makeEditedFileName('\r\n')).toBe('edited.pdf');
        expect(makeEditedFileName('   ')).toBe('edited.pdf');
    });
});
