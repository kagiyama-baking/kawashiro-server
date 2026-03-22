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
import { convertImage, zipToPdf } from '@/lib/api/media';

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
});
