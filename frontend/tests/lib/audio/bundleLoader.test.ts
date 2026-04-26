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
import {
    countPlayableAudios,
    isAllWav,
    loadSessionAudios,
} from '@/lib/audio/bundleLoader';
import type { ChatSessionMessage } from '@/types/talk';

const SESSION_ID = 'sess-1';

function makeMsg(
    overrides: Partial<ChatSessionMessage>,
): ChatSessionMessage {
    return {
        id: 1,
        sequence: 0,
        role: 'assistant',
        content: '',
        audio_url: null,
        audio_format: '',
        audio_size_bytes: 0,
        created_at: '2026-04-26T00:00:00Z',
        ...overrides,
    };
}

const server = setupServer(
    http.get(`*/api/talk/sessions/${SESSION_ID}/audio/:msgId/`, ({ params }) =>
        HttpResponse.arrayBuffer(
            new Uint8Array([1, 2, 3, Number(params.msgId)]).buffer,
            { headers: { 'Content-Type': 'audio/wav' } },
        ),
    ),
);

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('countPlayableAudios', () => {
    it('audio_url と audio_size_bytes>0 の件数を返す', () => {
        const msgs: ChatSessionMessage[] = [
            makeMsg({ id: 1 }),
            makeMsg({ id: 2, audio_url: 'x', audio_size_bytes: 100 }),
            makeMsg({ id: 3, audio_url: 'x', audio_size_bytes: 0 }),
            makeMsg({ id: 4, audio_url: 'x', audio_size_bytes: 50 }),
        ];
        expect(countPlayableAudios(msgs)).toBe(2);
    });
});

describe('isAllWav', () => {
    it('全件 wav なら true', () => {
        expect(
            isAllWav([
                { blob: new Blob(), format: 'wav' },
                { blob: new Blob(), format: 'wav' },
            ]),
        ).toBe(true);
    });
    it('1 件でも wav 以外があれば false', () => {
        expect(
            isAllWav([
                { blob: new Blob(), format: 'wav' },
                { blob: new Blob(), format: 'mp3' },
            ]),
        ).toBe(false);
    });
    it('空配列は false', () => {
        expect(isAllWav([])).toBe(false);
    });
});

describe('loadSessionAudios', () => {
    it('audio_url を持つメッセージ全件を fetch して FetchedAudio[] を返す', async () => {
        const msgs: ChatSessionMessage[] = [
            makeMsg({ id: 1 }), // skipped
            makeMsg({
                id: 2,
                audio_url: 'x',
                audio_size_bytes: 4,
                audio_format: 'wav',
            }),
            makeMsg({
                id: 3,
                audio_url: 'x',
                audio_size_bytes: 4,
                audio_format: 'mp3',
            }),
            makeMsg({ id: 4, audio_url: 'x', audio_size_bytes: 0 }), // skipped
        ];
        const result = await loadSessionAudios(SESSION_ID, msgs);
        expect(result).toHaveLength(2);
        expect(result[0].format).toBe('wav');
        expect(result[1].format).toBe('mp3');
        expect(result[0].blob.size).toBe(4);
    });

    it('対象ゼロなら空配列', async () => {
        const result = await loadSessionAudios(SESSION_ID, []);
        expect(result).toEqual([]);
    });
});
