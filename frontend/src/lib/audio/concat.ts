/**
 * WAV / 音声 Blob 結合ユーティリティ.
 */

interface WavDataChunkInfo {
    readonly dataStart: number;
    readonly dataSize: number;
    readonly headerEnd: number;
}

interface WavFmtInfo {
    readonly numChannels: number;
    readonly sampleRate: number;
    readonly blockAlign: number;
    readonly bitsPerSample: number;
}

/**
 * RIFF/WAV バッファから "fmt " チャンクの主要フィールドを読み出す.
 * 無音バイト数の算出に使う。
 */
function findFmtChunk(buffer: ArrayBuffer): WavFmtInfo {
    const view = new DataView(buffer);
    let offset = 12;
    while (offset + 8 <= buffer.byteLength) {
        const chunkId = String.fromCharCode(
            view.getUint8(offset),
            view.getUint8(offset + 1),
            view.getUint8(offset + 2),
            view.getUint8(offset + 3),
        );
        const chunkSize = view.getUint32(offset + 4, true);
        if (chunkId === 'fmt ') {
            // fmt 本体は offset+8 から始まる
            return {
                numChannels: view.getUint16(offset + 10, true),
                sampleRate: view.getUint32(offset + 12, true),
                blockAlign: view.getUint16(offset + 20, true),
                bitsPerSample: view.getUint16(offset + 22, true),
            };
        }
        offset += 8 + chunkSize;
    }
    throw new Error('WAV の fmt チャンクが見つかりません');
}

/**
 * RIFF/WAV バッファから "data" チャンクの位置とサイズを返す.
 * 同時に "data" チャンク開始位置（= ヘッダ終端）も返す。
 */
function findDataChunk(buffer: ArrayBuffer): WavDataChunkInfo {
    const view = new DataView(buffer);
    if (buffer.byteLength < 12) {
        throw new Error('WAV が短すぎます');
    }
    const riffId = String.fromCharCode(
        view.getUint8(0),
        view.getUint8(1),
        view.getUint8(2),
        view.getUint8(3),
    );
    const waveId = String.fromCharCode(
        view.getUint8(8),
        view.getUint8(9),
        view.getUint8(10),
        view.getUint8(11),
    );
    if (riffId !== 'RIFF' || waveId !== 'WAVE') {
        throw new Error('RIFF/WAVE ヘッダが見つかりません');
    }

    let offset = 12;
    while (offset + 8 <= buffer.byteLength) {
        const chunkId = String.fromCharCode(
            view.getUint8(offset),
            view.getUint8(offset + 1),
            view.getUint8(offset + 2),
            view.getUint8(offset + 3),
        );
        const chunkSize = view.getUint32(offset + 4, true);
        if (chunkId === 'data') {
            return {
                dataStart: offset + 8,
                dataSize: chunkSize,
                headerEnd: offset,
            };
        }
        offset += 8 + chunkSize;
    }
    throw new Error('WAV の data チャンクが見つかりません');
}

/**
 * 同フォーマットの WAV Blob を結合する.
 *
 * 各 WAV の data チャンクを連結し、最初の WAV の RIFF/fmt ヘッダを再利用する。
 * fmt チャンクの整合性は呼び出し側で保証すること（同じ TTS 設定で生成された
 * WAV の前提）。
 *
 * `silenceSeconds` を指定すると、各 WAV の間に PCM 0 埋め（無音）バイトを
 * 挿入する。サンプルレート/チャンネル数/ビット深度は 1 つ目の WAV の fmt
 * チャンクから読み出す。
 */
export async function concatWavBlobs(
    blobs: Blob[],
    silenceSeconds: number = 0,
): Promise<Blob> {
    if (blobs.length === 0) {
        throw new Error('結合する WAV がありません');
    }
    if (blobs.length === 1) {
        return blobs[0];
    }

    const buffers = await Promise.all(blobs.map((b) => b.arrayBuffer()));

    let silenceBytes = 0;
    if (silenceSeconds > 0) {
        const fmt = findFmtChunk(buffers[0]);
        const blockAlign =
            fmt.blockAlign || (fmt.numChannels * fmt.bitsPerSample) / 8;
        const raw = Math.round(silenceSeconds * fmt.sampleRate * blockAlign);
        // PCM フレーム境界を保つよう blockAlign の倍数に揃える
        silenceBytes =
            blockAlign > 0 ? Math.floor(raw / blockAlign) * blockAlign : 0;
    }
    const silenceChunk = silenceBytes > 0 ? new Uint8Array(silenceBytes) : null;

    const dataChunks: Uint8Array[] = [];
    let totalDataSize = 0;
    let firstHeaderEnd = 0;

    for (let i = 0; i < buffers.length; i++) {
        const { dataStart, dataSize, headerEnd } = findDataChunk(buffers[i]);
        if (i === 0) {
            firstHeaderEnd = headerEnd;
        } else if (silenceChunk !== null) {
            dataChunks.push(silenceChunk);
            totalDataSize += silenceChunk.byteLength;
        }
        dataChunks.push(new Uint8Array(buffers[i], dataStart, dataSize));
        totalDataSize += dataSize;
    }

    // 最初の WAV のヘッダ（"data" チャンク直前まで）を再利用
    const headerPart = new Uint8Array(buffers[0], 0, firstHeaderEnd);
    const totalSize = headerPart.byteLength + 8 + totalDataSize;

    const result = new Uint8Array(totalSize);
    result.set(headerPart, 0);

    const resultView = new DataView(result.buffer);
    // RIFF size = total - 8
    resultView.setUint32(4, totalSize - 8, true);

    // "data" + size
    result[headerPart.byteLength] = 0x64; // 'd'
    result[headerPart.byteLength + 1] = 0x61; // 'a'
    result[headerPart.byteLength + 2] = 0x74; // 't'
    result[headerPart.byteLength + 3] = 0x61; // 'a'
    resultView.setUint32(headerPart.byteLength + 4, totalDataSize, true);

    let offset = headerPart.byteLength + 8;
    for (const chunk of dataChunks) {
        result.set(chunk, offset);
        offset += chunk.byteLength;
    }

    return new Blob([result], { type: 'audio/wav' });
}

/**
 * Date を YYYYMMDD-HHmmss 形式の文字列に変換する.
 */
export function formatTimestampForFilename(d: Date): string {
    const pad = (n: number) => String(n).padStart(2, '0');
    return (
        `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}` +
        `-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
    );
}
