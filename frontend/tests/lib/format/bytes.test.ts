import { describe, expect, it } from 'vitest';
import { formatBytes } from '@/lib/format/bytes';

describe('formatBytes', () => {
    it('0 や負数は "0 B"', () => {
        expect(formatBytes(0)).toBe('0 B');
        expect(formatBytes(-100)).toBe('0 B');
    });

    it('B 単位 (1024 未満)', () => {
        expect(formatBytes(1)).toBe('1 B');
        expect(formatBytes(1023)).toBe('1023 B');
    });

    it('KB 単位（1 桁は小数 1 桁、2 桁以上は整数）', () => {
        expect(formatBytes(1024)).toBe('1.0 KB');
        expect(formatBytes(2048)).toBe('2.0 KB');
        expect(formatBytes(10 * 1024)).toBe('10 KB');
        expect(formatBytes(123 * 1024)).toBe('123 KB');
    });

    it('MB 単位', () => {
        expect(formatBytes(1024 * 1024)).toBe('1.0 MB');
        expect(formatBytes(15 * 1024 * 1024)).toBe('15 MB');
    });

    it('GB 単位（最大）', () => {
        expect(formatBytes(2 * 1024 ** 3)).toBe('2.0 GB');
        expect(formatBytes(100 * 1024 ** 3)).toBe('100 GB');
    });
});
