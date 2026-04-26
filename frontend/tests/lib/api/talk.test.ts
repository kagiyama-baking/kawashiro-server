import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import {
    bulkDeleteAudio,
    createSession,
    deleteAudio,
    deleteSession,
    editMessage,
    fetchAudioBlob,
    fetchConfigs,
    getSession,
    listSessions,
    postMessage,
    updateSessionTitle,
} from '@/lib/api/talk';

const SESSION_ID = '123e4567-e89b-12d3-a456-426614174000';
const MSG_ID = 42;

let lastBody: Record<string, unknown> | null = null;
let lastSearch: URLSearchParams | null = null;

const baseSession = {
    id: SESSION_ID,
    title: 't',
    config_name: 'morning',
    message_count: 0,
    total_audio_bytes: 0,
    created_at: '2026-04-26T00:00:00Z',
    updated_at: '2026-04-26T00:00:00Z',
    messages: [],
};

const server = setupServer(
    http.get('*/api/talk/configs/', () =>
        HttpResponse.json({
            configs: [
                {
                    name: 'morning',
                    display_name: '朝のあいさつ',
                    tts_enabled: true,
                },
            ],
        }),
    ),
    http.get('*/api/talk/sessions/', ({ request }) => {
        lastSearch = new URL(request.url).searchParams;
        return HttpResponse.json({
            count: 5,
            next: null,
            previous: null,
            results: [
                {
                    id: SESSION_ID,
                    title: '雑談',
                    config_name: 'morning',
                    message_count: 4,
                    total_audio_bytes: 2048,
                    created_at: '2026-04-26T00:00:00Z',
                    updated_at: '2026-04-26T01:00:00Z',
                },
            ],
        });
    }),
    http.post('*/api/talk/sessions/', async ({ request }) => {
        lastBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(baseSession, { status: 201 });
    }),
    http.get(`*/api/talk/sessions/${SESSION_ID}/`, () =>
        HttpResponse.json(baseSession),
    ),
    http.patch(`*/api/talk/sessions/${SESSION_ID}/`, async ({ request }) => {
        lastBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...baseSession, title: '新タイトル' });
    }),
    http.delete(
        `*/api/talk/sessions/${SESSION_ID}/`,
        () => new HttpResponse(null, { status: 204 }),
    ),
    http.post(
        `*/api/talk/sessions/${SESSION_ID}/messages/`,
        async ({ request }) => {
            lastBody = (await request.json()) as Record<string, unknown>;
            return HttpResponse.json(baseSession, { status: 201 });
        },
    ),
    http.patch(
        `*/api/talk/sessions/${SESSION_ID}/messages/${MSG_ID}/`,
        async ({ request }) => {
            lastBody = (await request.json()) as Record<string, unknown>;
            return HttpResponse.json(baseSession);
        },
    ),
    http.get(`*/api/talk/sessions/${SESSION_ID}/audio/${MSG_ID}/`, () =>
        HttpResponse.arrayBuffer(new Uint8Array([1, 2, 3, 4]).buffer, {
            headers: { 'Content-Type': 'audio/wav' },
        }),
    ),
    http.delete(
        `*/api/talk/sessions/${SESSION_ID}/audio/${MSG_ID}/`,
        () => new HttpResponse(null, { status: 204 }),
    ),
    http.delete(
        `*/api/talk/sessions/${SESSION_ID}/audio/`,
        () => new HttpResponse(null, { status: 204 }),
    ),
);

beforeAll(() => server.listen());
afterEach(() => {
    server.resetHandlers();
    lastBody = null;
    lastSearch = null;
});
afterAll(() => server.close());

describe('Talk API', () => {
    it('設定一覧を取得できる', async () => {
        const configs = await fetchConfigs();
        expect(configs[0].name).toBe('morning');
    });

    it('セッション一覧を取得できる（ページネーション付き）', async () => {
        const res = await listSessions({ limit: 10, offset: 5 });
        expect(res.count).toBe(5);
        expect(res.results[0].title).toBe('雑談');
        expect(lastSearch?.get('limit')).toBe('10');
        expect(lastSearch?.get('offset')).toBe('5');
    });

    it('セッションを新規作成できる', async () => {
        const detail = await createSession('morning');
        expect(detail.id).toBe(SESSION_ID);
        expect(lastBody).toEqual({ config_name: 'morning' });
    });

    it('セッション詳細を取得できる', async () => {
        const detail = await getSession(SESSION_ID);
        expect(detail.id).toBe(SESSION_ID);
    });

    it('セッションタイトルを更新できる', async () => {
        const detail = await updateSessionTitle(SESSION_ID, '新タイトル');
        expect(detail.title).toBe('新タイトル');
        expect(lastBody).toEqual({ title: '新タイトル' });
    });

    it('セッションを削除できる', async () => {
        await expect(deleteSession(SESSION_ID)).resolves.toBeUndefined();
    });

    it('メッセージ送信ができる', async () => {
        const detail = await postMessage(SESSION_ID, 'おはよう');
        expect(detail.id).toBe(SESSION_ID);
        expect(lastBody).toEqual({ content: 'おはよう' });
    });

    it('メッセージ送信は AbortSignal で中断できる', async () => {
        server.use(
            http.post(
                `*/api/talk/sessions/${SESSION_ID}/messages/`,
                async () => {
                    await new Promise((r) => setTimeout(r, 200));
                    return HttpResponse.json(baseSession, { status: 201 });
                },
            ),
        );
        const controller = new AbortController();
        const promise = postMessage(SESSION_ID, 'x', {
            signal: controller.signal,
        });
        controller.abort();
        await expect(promise).rejects.toMatchObject({ name: 'AbortError' });
    });

    it('メッセージを編集再送できる', async () => {
        const detail = await editMessage(SESSION_ID, MSG_ID, '直し');
        expect(detail.id).toBe(SESSION_ID);
        expect(lastBody).toEqual({ content: '直し' });
    });

    it('音声 Blob を取得できる', async () => {
        const blob = await fetchAudioBlob(SESSION_ID, MSG_ID);
        expect(blob.size).toBe(4);
        expect(blob.type).toBe('audio/wav');
    });

    it('個別音声を削除できる', async () => {
        await expect(deleteAudio(SESSION_ID, MSG_ID)).resolves.toBeUndefined();
    });

    it('音声を一括削除できる', async () => {
        await expect(bulkDeleteAudio(SESSION_ID)).resolves.toBeUndefined();
    });
});
