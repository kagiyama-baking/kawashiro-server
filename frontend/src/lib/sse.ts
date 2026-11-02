/** Server-Sent Events の 1 イベント。data は JSON などの解釈をせずそのまま渡す。 */
export interface ServerSentEvent {
    readonly event: string;
    readonly data: string;
}

interface SplitResult {
    readonly lines: readonly string[];
    readonly rest: string;
}

/**
 * 完成した行と、次のチャンクを待つ残りに分ける。
 * 末尾の CR は次のチャンクの LF と対かもしれないので、行にせず残りへ回す。
 */
function splitLines(buffer: string): SplitResult {
    const lines: string[] = [];
    let start = 0;
    for (let i = 0; i < buffer.length; i++) {
        const char = buffer[i];
        if (char === '\n') {
            lines.push(buffer.slice(start, i));
            start = i + 1;
        } else if (char === '\r') {
            if (i + 1 === buffer.length) break;
            lines.push(buffer.slice(start, i));
            if (buffer[i + 1] === '\n') i++;
            start = i + 1;
        }
    }
    return { lines, rest: buffer.slice(start) };
}

async function* readLines(
    body: ReadableStream<Uint8Array>,
): AsyncGenerator<string> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finished = false;
    try {
        for (;;) {
            const { done, value } = await reader.read();
            if (done) {
                finished = true;
                break;
            }
            const { lines, rest } = splitLines(
                buffer + decoder.decode(value, { stream: true }),
            );
            buffer = rest;
            yield* lines;
        }
        // 残った CR は、もう次のチャンクが来ないので行末として確定する
        const tail = buffer + decoder.decode();
        if (tail.endsWith('\r')) yield tail.slice(0, -1);
    } finally {
        // 途中でやめたら本文を取り消して接続を閉じる。
        // tee の相手が残っていると完了しないことがあるので、待たずに進める。
        if (!finished) reader.cancel().catch(() => {});
    }
}

/**
 * レスポンス本文を Server-Sent Events として読む。
 * WHATWG の解釈に従い、空行で終わっていない末尾のイベントは捨てる。
 */
export async function* parseEventStream(
    body: ReadableStream<Uint8Array>,
): AsyncGenerator<ServerSentEvent> {
    let event = '';
    let data: readonly string[] = [];
    for await (const line of readLines(body)) {
        if (line === '') {
            if (data.length > 0) {
                yield { event: event || 'message', data: data.join('\n') };
            }
            event = '';
            data = [];
            continue;
        }
        if (line.startsWith(':')) continue;

        const colon = line.indexOf(':');
        const field = colon === -1 ? line : line.slice(0, colon);
        const raw = colon === -1 ? '' : line.slice(colon + 1);
        const value = raw.startsWith(' ') ? raw.slice(1) : raw;
        if (field === 'event') event = value;
        if (field === 'data') data = [...data, value];
    }
}
