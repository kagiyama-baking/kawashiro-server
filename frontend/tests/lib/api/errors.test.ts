import { HTTPError, type NormalizedOptions } from 'ky';
import { describe, expect, it } from 'vitest';
import { extractApiErrorMessage } from '@/lib/api/errors';

function httpError(body: unknown, status = 400): HTTPError {
    const request = new Request('http://localhost/api/x');
    const response = new Response(
        typeof body === 'string' ? body : JSON.stringify(body),
        { status },
    );
    return new HTTPError(response, request, {} as NormalizedOptions);
}

describe('extractApiErrorMessage', () => {
    it('error の文言を返す', async () => {
        await expect(
            extractApiErrorMessage(httpError({ error: '上限です' }), 'fb'),
        ).resolves.toBe('上限です');
    });

    it('スロットルなどの detail の文言を返す', async () => {
        await expect(
            extractApiErrorMessage(
                httpError({ detail: 'リクエストが多すぎます' }, 429),
                'fb',
            ),
        ).resolves.toBe('リクエストが多すぎます');
    });

    it('DRF の項目エラーの先頭の文言を返す', async () => {
        await expect(
            extractApiErrorMessage(
                httpError({ content: ['4000 文字以内にしてください', '別'] }),
                'fb',
            ),
        ).resolves.toBe('4000 文字以内にしてください');
    });

    it('error を detail と項目エラーより優先する', async () => {
        await expect(
            extractApiErrorMessage(
                httpError({ content: ['項目'], detail: '詳細', error: '本命' }),
                'fb',
            ),
        ).resolves.toBe('本命');
    });

    it.each([
        ['空の error', { error: '  ' }],
        ['文字列でない error', { error: 1 }],
        ['空のオブジェクト', {}],
        ['空の項目エラー', { content: [] }],
        ['文字列でない項目エラー', { content: [{ code: 'x' }] }],
        ['オブジェクトでない本文', 'null'],
        ['配列の本文', ['x']],
    ])('%s なら fallback を返す', async (_name, body) => {
        await expect(
            extractApiErrorMessage(httpError(body), 'fb'),
        ).resolves.toBe('fb');
    });

    it('JSON でない本文なら fallback を返す', async () => {
        await expect(
            extractApiErrorMessage(httpError('<html>', 500), 'fb'),
        ).resolves.toBe('fb');
    });

    it('HTTPError でない例外なら fallback を返す', async () => {
        await expect(
            extractApiErrorMessage(new Error('network'), 'fb'),
        ).resolves.toBe('fb');
    });
});
