import { HTTPError } from 'ky';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import {
    afterAll,
    afterEach,
    beforeAll,
    describe,
    expect,
    it,
    vi,
} from 'vitest';
import { extractApiErrorMessage } from '@/lib/api/errors';
import {
    bulkDeleteAudio,
    createSession,
    deleteAudio,
    deleteSession,
    fetchAudioBlob,
    fetchConfigs,
    getSession,
    listSessions,
    streamEdit,
    streamMessage,
    updateSessionTitle,
} from '@/lib/api/talk';
import type { ChatStreamEvent } from '@/types/talk';

const SESSION_ID = '123e4567-e89b-12d3-a456-426614174000';
const MSG_ID = 42;
const SSE_HEADERS = { 'Content-Type': 'text/event-stream' };

let lastBody: Record<string, unknown> | null = null;
let lastSearch: URLSearchParams | null = null;
let lastAccept: string | null = null;

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

const savedMessage = {
    id: 7,
    sequence: 0,
    role: 'user',
    content: 'おはよう',
    audio_url: null,
    audio_format: '',
    audio_size_bytes: 0,
    created_at: '2026-04-26T00:00:00Z',
};

function frame(event: string, data: unknown): string {
    return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function sseBody(...frames: readonly string[]): ReadableStream<Uint8Array> {
    const encoder = new TextEncoder();
    return new ReadableStream<Uint8Array>({
        start(controller) {
            for (const text of frames) {
                controller.enqueue(encoder.encode(text));
            }
            controller.close();
        },
    });
}

async function collect(
    stream: AsyncIterable<ChatStreamEvent>,
): Promise<ChatStreamEvent[]> {
    const events: ChatStreamEvent[] = [];
    for await (const event of stream) {
        events.push(event);
    }
    return events;
}

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
            lastAccept = request.headers.get('Accept');
            return new HttpResponse(
                sseBody(
                    frame('start', {}),
                    frame('delta', { text: 'おは' }),
                    frame('delta', { text: 'よう' }),
                    frame('message', {
                        user: savedMessage,
                        assistant: {
                            ...savedMessage,
                            id: 8,
                            sequence: 1,
                            role: 'assistant',
                        },
                    }),
                    frame('done', {
                        title: '',
                        message_count: 2,
                        total_audio_bytes: 0,
                        updated_at: '2026-04-26T00:00:01Z',
                    }),
                ),
                { headers: SSE_HEADERS },
            );
        },
    ),
    http.patch(
        `*/api/talk/sessions/${SESSION_ID}/messages/${MSG_ID}/`,
        async ({ request }) => {
            lastBody = (await request.json()) as Record<string, unknown>;
            lastAccept = request.headers.get('Accept');
            return new HttpResponse(
                sseBody(frame('start', {}), frame('delta', { text: '直し' })),
                { headers: SSE_HEADERS },
            );
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
    vi.unstubAllGlobals();
    server.resetHandlers();
    lastBody = null;
    lastSearch = null;
    lastAccept = null;
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

    describe('streamMessage', () => {
        it('本文を送り、SSE のイベントを順に返す', async () => {
            const events = await collect(streamMessage(SESSION_ID, 'おはよう'));

            expect(lastBody).toEqual({ content: 'おはよう' });
            expect(events.map((e) => e.type)).toEqual([
                'start',
                'delta',
                'delta',
                'message',
                'done',
            ]);
            expect(events[1]).toEqual({ type: 'delta', text: 'おは' });
            expect(events[3]).toMatchObject({
                type: 'message',
                user: { id: 7 },
                assistant: { id: 8 },
            });
        });

        // JSONRenderer のみの DRF は text/event-stream 単独の指定に 406 を返す
        it('Accept に text/event-stream と application/json の両方を付ける', async () => {
            await collect(streamMessage(SESSION_ID, 'x'));

            expect(lastAccept).toBe('text/event-stream, application/json');
        });

        it('未知のイベントと JSON でない data を読み飛ばす', async () => {
            server.use(
                http.post(
                    `*/api/talk/sessions/${SESSION_ID}/messages/`,
                    () =>
                        new HttpResponse(
                            sseBody(
                                frame('ping', {}),
                                'event: delta\ndata: {壊れている\n\n',
                                'event: delta\ndata: 3\n\n',
                                frame('delta', { text: '届く' }),
                            ),
                            { headers: SSE_HEADERS },
                        ),
                ),
            );

            const events = await collect(streamMessage(SESSION_ID, 'x'));

            expect(events).toEqual([{ type: 'delta', text: '届く' }]);
        });

        it('事前検証のエラーは HTTPError として投げ、サーバーの文言を読める', async () => {
            server.use(
                http.post(`*/api/talk/sessions/${SESSION_ID}/messages/`, () =>
                    HttpResponse.json(
                        { error: 'メッセージ数上限に達しました' },
                        { status: 400 },
                    ),
                ),
            );

            const caught = await collect(streamMessage(SESSION_ID, 'x')).catch(
                (e: unknown) => e,
            );

            expect(caught).toBeInstanceOf(HTTPError);
            await expect(
                extractApiErrorMessage(caught, 'fallback'),
            ).resolves.toBe('メッセージ数上限に達しました');
        });

        it('応答を待っている間に AbortSignal で中断できる', async () => {
            server.use(
                http.post(
                    `*/api/talk/sessions/${SESSION_ID}/messages/`,
                    async () => {
                        await new Promise((r) => setTimeout(r, 200));
                        return new HttpResponse(null, { status: 200 });
                    },
                ),
            );
            const controller = new AbortController();

            const pending = collect(
                streamMessage(SESSION_ID, 'x', { signal: controller.signal }),
            );
            controller.abort();

            await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
        });

        // msw は応答後の中断を本文へ伝えないので、ブラウザと同じ振る舞いの fetch に差し替える
        it('本文を読んでいる間に AbortSignal で中断できる', async () => {
            vi.stubGlobal(
                'fetch',
                vi.fn(async (request: Request) => {
                    const body = new ReadableStream<Uint8Array>({
                        start(stream) {
                            stream.enqueue(
                                new TextEncoder().encode(frame('start', {})),
                            );
                            request.signal.addEventListener('abort', () => {
                                stream.error(request.signal.reason);
                            });
                        },
                    });
                    return new Response(body, { headers: SSE_HEADERS });
                }),
            );
            const controller = new AbortController();
            const stream = streamMessage(SESSION_ID, 'x', {
                signal: controller.signal,
            });

            await expect(stream.next()).resolves.toMatchObject({
                value: { type: 'start' },
            });
            const pending = stream.next();
            controller.abort();

            await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
        });

        it('本文のないレスポンスは何も返さず終わる', async () => {
            server.use(
                http.post(
                    `*/api/talk/sessions/${SESSION_ID}/messages/`,
                    () => new HttpResponse(null, { status: 200 }),
                ),
            );

            await expect(
                collect(streamMessage(SESSION_ID, 'x')),
            ).resolves.toEqual([]);
        });
    });

    describe('streamEdit', () => {
        it('編集した本文を PATCH で送り、SSE のイベントを返す', async () => {
            const events = await collect(
                streamEdit(SESSION_ID, MSG_ID, '直し'),
            );

            expect(lastBody).toEqual({ content: '直し' });
            expect(lastAccept).toBe('text/event-stream, application/json');
            expect(events).toEqual([
                { type: 'start' },
                { type: 'delta', text: '直し' },
            ]);
        });
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
