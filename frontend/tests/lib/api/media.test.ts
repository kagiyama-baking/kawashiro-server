import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import {
    afterAll,
    afterEach,
    beforeAll,
    describe,
    expect,
    it,
} from 'vitest';
import { convertImage, extractApiErrorMessage, zipToPdf } from '@/lib/api/media';

const server = setupServer(
    http.post('*/api/media/convert-image/', () => {
        return new HttpResponse('fake-image-data', {
            status: 200,
            headers: {
                'Content-Type': 'image/png',
                'Content-Disposition':
                    'attachment; filename="20260322.800x600.png"',
            },
        });
    }),
    http.post('*/api/media/zip-to-pdf/', () => {
        return new HttpResponse('fake-pdf-data', {
            status: 200,
            headers: {
                'Content-Type': 'application/pdf',
                'Content-Disposition':
                    'attachment; filename="converted.pdf"',
            },
        });
    }),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('Media API', () => {
    it('画像変換でBlobが返る', async () => {
        const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' });
        const result = await convertImage({
            file,
            output_format: 'png',
            quality: 85,
        });

        expect(result.blob.size).toBeGreaterThan(0);
        expect(result.filename).toBe('20260322.800x600.png');
    });

    it('ZIP→PDF変換でBlobが返る', async () => {
        const file = new File(['test'], 'test.zip', {
            type: 'application/zip',
        });
        const result = await zipToPdf(file);

        expect(result.blob.size).toBeGreaterThan(0);
        expect(result.filename).toBe('converted.pdf');
    });

    it('半角スペース・括弧・記号を含むファイル名も filename* からデコードできる', async () => {
        server.use(
            http.post('*/api/media/zip-to-pdf/', () => {
                return new HttpResponse('fake-pdf-data', {
                    status: 200,
                    headers: {
                        'Content-Type': 'application/pdf',
                        'Content-Disposition':
                            "attachment; filename=\"my-file_v2 (final) [draft].pdf\"; filename*=UTF-8''my-file_v2%20%28final%29%20%5Bdraft%5D.pdf",
                    },
                });
            }),
        );

        const file = new File(['test'], 'my-file_v2 (final) [draft].zip', {
            type: 'application/zip',
        });
        const result = await zipToPdf(file);

        expect(result.filename).toBe('my-file_v2 (final) [draft].pdf');
    });

    it('ZIP→PDFのファイル名は RFC 5987 (filename*=UTF-8\'\'…) を優先して日本語をデコードする', async () => {
        server.use(
            http.post('*/api/media/zip-to-pdf/', () => {
                return new HttpResponse('fake-pdf-data', {
                    status: 200,
                    headers: {
                        'Content-Type': 'application/pdf',
                        'Content-Disposition':
                            "attachment; filename=\"_____.pdf\"; filename*=UTF-8''%E3%81%82%E3%81%84%E3%81%86%E3%81%88%E3%81%8A.pdf",
                    },
                });
            }),
        );

        const file = new File(['test'], 'あいうえお.zip', {
            type: 'application/zip',
        });
        const result = await zipToPdf(file);

        expect(result.filename).toBe('あいうえお.pdf');
    });

    it('extractApiErrorMessage は ky の HTTPError から error フィールドを取り出す', async () => {
        server.use(
            http.post('*/api/media/zip-to-pdf/', () => {
                return HttpResponse.json(
                    {
                        error: 'サーバーのメモリが不足しました。画像の枚数を減らすか、解像度を下げて再試行してください',
                    },
                    { status: 503 },
                );
            }),
        );

        const file = new File(['test'], 'big.zip', {
            type: 'application/zip',
        });
        let caught: unknown = null;
        try {
            await zipToPdf(file);
        } catch (e) {
            caught = e;
        }

        const msg = await extractApiErrorMessage(caught, 'fallback');
        expect(msg).toContain('メモリ');
    });

    it('extractApiErrorMessage はJSONでないボディの場合はfallbackを返す', async () => {
        server.use(
            http.post('*/api/media/zip-to-pdf/', () => {
                return new HttpResponse('not json', { status: 500 });
            }),
        );

        const file = new File(['test'], 't.zip', {
            type: 'application/zip',
        });
        let caught: unknown = null;
        try {
            await zipToPdf(file);
        } catch (e) {
            caught = e;
        }

        const msg = await extractApiErrorMessage(caught, 'fallback文言');
        expect(msg).toBe('fallback文言');
    });

    it('extractApiErrorMessage は HTTPError でない例外の場合は fallback を返す', async () => {
        const msg = await extractApiErrorMessage(
            new Error('network down'),
            'fallback文言',
        );
        expect(msg).toBe('fallback文言');
    });
});
