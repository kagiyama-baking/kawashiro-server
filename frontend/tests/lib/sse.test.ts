import { describe, expect, it, vi } from 'vitest';
import { parseEventStream, type ServerSentEvent } from '@/lib/sse';

const encoder = new TextEncoder();

/** 与えた断片をそのまま 1 チャンクずつ流すストリームを作る。 */
function streamOf(
    chunks: readonly (string | Uint8Array)[],
): ReadableStream<Uint8Array> {
    return new ReadableStream<Uint8Array>({
        start(controller) {
            for (const chunk of chunks) {
                controller.enqueue(
                    typeof chunk === 'string' ? encoder.encode(chunk) : chunk,
                );
            }
            controller.close();
        },
    });
}

async function collect(
    body: ReadableStream<Uint8Array>,
): Promise<ServerSentEvent[]> {
    const events: ServerSentEvent[] = [];
    for await (const event of parseEventStream(body)) {
        events.push(event);
    }
    return events;
}

describe('parseEventStream', () => {
    it('event と data の組を順に返す', async () => {
        const events = await collect(
            streamOf([
                'event: start\ndata: {}\n\n',
                'event: delta\ndata: {"text":"こんにちは"}\n\n',
            ]),
        );

        expect(events).toEqual([
            { event: 'start', data: '{}' },
            { event: 'delta', data: '{"text":"こんにちは"}' },
        ]);
    });

    it('チャンクがイベントの途中で切れても 1 つのイベントとして組み立てる', async () => {
        const events = await collect(
            streamOf(['eve', 'nt: del', 'ta\nda', 'ta: {"t":1}\n', '\n']),
        );

        expect(events).toEqual([{ event: 'delta', data: '{"t":1}' }]);
    });

    it('マルチバイト文字がチャンクの境界で分割されても文字化けしない', async () => {
        const bytes = encoder.encode('event: delta\ndata: 鍵山製パン\n\n');
        // 「鍵」の 3 バイトの途中で切る
        const splitAt = encoder.encode('event: delta\ndata: ').length + 1;

        const events = await collect(
            streamOf([bytes.slice(0, splitAt), bytes.slice(splitAt)]),
        );

        expect(events).toEqual([{ event: 'delta', data: '鍵山製パン' }]);
    });

    it('コメント行を無視する', async () => {
        const events = await collect(
            streamOf([': ping\n\n', ': hello\nevent: start\ndata: {}\n\n']),
        );

        expect(events).toEqual([{ event: 'start', data: '{}' }]);
    });

    it('複数行の data を改行でつなぐ', async () => {
        const events = await collect(
            streamOf(['event: delta\ndata: 1 行目\ndata: 2 行目\n\n']),
        );

        expect(events).toEqual([{ event: 'delta', data: '1 行目\n2 行目' }]);
    });

    it('event がなければ message として扱う', async () => {
        const events = await collect(streamOf(['data: {}\n\n']));

        expect(events).toEqual([{ event: 'message', data: '{}' }]);
    });

    it('CRLF と CR の改行も扱い、チャンク境界の CRLF を 2 行に数えない', async () => {
        const events = await collect(
            streamOf([
                'event: a\r\ndata: 1\r\n\r',
                '\nevent: b\rdata: 2\r\r',
                'event: c\r',
                '\ndata: 3\r\n\r\n',
            ]),
        );

        expect(events).toEqual([
            { event: 'a', data: '1' },
            { event: 'b', data: '2' },
            { event: 'c', data: '3' },
        ]);
    });

    it('コロンのない行は値が空の項目として扱う', async () => {
        const events = await collect(
            streamOf(['data\ndata: x\n\n', 'data\n\n']),
        );

        expect(events).toEqual([
            { event: 'message', data: '\nx' },
            { event: 'message', data: '' },
        ]);
    });

    it('値の先頭の空白は 1 つだけ取り除く', async () => {
        const events = await collect(
            streamOf(['data:  二つ\n\n', 'data:なし\n\n']),
        );

        expect(events).toEqual([
            { event: 'message', data: ' 二つ' },
            { event: 'message', data: 'なし' },
        ]);
    });

    it('data のないイベントは無視し、次のイベントへ event を持ち越さない', async () => {
        const events = await collect(
            streamOf(['event: ghost\n\n', 'data: {}\n\n']),
        );

        expect(events).toEqual([{ event: 'message', data: '{}' }]);
    });

    it('未知の項目を無視する', async () => {
        const events = await collect(
            streamOf(['id: 1\nretry: 3000\nevent: a\ndata: 1\n\n']),
        );

        expect(events).toEqual([{ event: 'a', data: '1' }]);
    });

    it('先頭の BOM を無視する', async () => {
        const events = await collect(streamOf(['﻿event: a\ndata: 1\n\n']));

        expect(events).toEqual([{ event: 'a', data: '1' }]);
    });

    it('空行のないまま終わった末尾のイベントは捨てる', async () => {
        const events = await collect(
            streamOf(['event: a\ndata: 1\n\n', 'event: b\ndata: 2\n']),
        );

        expect(events).toEqual([{ event: 'a', data: '1' }]);
    });

    it('CR で終わるストリームの最後の空行を行末として確定する', async () => {
        const events = await collect(streamOf(['event: a\rdata: 1\r\r']));

        expect(events).toEqual([{ event: 'a', data: '1' }]);
    });

    it('読み取り中のエラーをそのまま投げる', async () => {
        const failure = new Error('切断');
        const body = new ReadableStream<Uint8Array>({
            start(controller) {
                controller.enqueue(encoder.encode('event: a\ndata: 1\n\n'));
            },
            pull(controller) {
                controller.error(failure);
            },
        });

        const received: ServerSentEvent[] = [];
        await expect(async () => {
            for await (const event of parseEventStream(body)) {
                received.push(event);
            }
        }).rejects.toBe(failure);
        expect(received).toEqual([{ event: 'a', data: '1' }]);
    });

    it('途中で読むのをやめると本文を取り消して接続を閉じる', async () => {
        const cancel = vi.fn();
        const body = new ReadableStream<Uint8Array>({
            start(controller) {
                controller.enqueue(encoder.encode('event: a\ndata: 1\n\n'));
            },
            cancel,
        });

        for await (const event of parseEventStream(body)) {
            expect(event.event).toBe('a');
            break;
        }

        expect(cancel).toHaveBeenCalledTimes(1);
    });

    it('読み終えた本文は取り消さない', async () => {
        const cancel = vi.fn();
        const body = new ReadableStream<Uint8Array>({
            start(controller) {
                controller.enqueue(encoder.encode('event: a\ndata: 1\n\n'));
                controller.close();
            },
            cancel,
        });

        await collect(body);

        expect(cancel).not.toHaveBeenCalled();
    });
});
