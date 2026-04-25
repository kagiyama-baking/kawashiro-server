import { describe, expect, it } from 'vitest';
import { concatWavBlobs, formatTimestampForFilename } from './concat';

function makeWavBuffer(samples: Uint8Array, sampleRate = 16000): ArrayBuffer {
    const numChannels = 1;
    const bitsPerSample = 16;
    const dataSize = samples.byteLength;
    const fmtChunkSize = 16;
    const totalSize = 4 + (8 + fmtChunkSize) + (8 + dataSize);

    const buffer = new ArrayBuffer(8 + totalSize);
    const view = new DataView(buffer);
    const u8 = new Uint8Array(buffer);

    // "RIFF"
    u8[0] = 0x52;
    u8[1] = 0x49;
    u8[2] = 0x46;
    u8[3] = 0x46;
    view.setUint32(4, totalSize, true);
    // "WAVE"
    u8[8] = 0x57;
    u8[9] = 0x41;
    u8[10] = 0x56;
    u8[11] = 0x45;

    // "fmt "
    u8[12] = 0x66;
    u8[13] = 0x6d;
    u8[14] = 0x74;
    u8[15] = 0x20;
    view.setUint32(16, fmtChunkSize, true);
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, (sampleRate * numChannels * bitsPerSample) / 8, true);
    view.setUint16(32, (numChannels * bitsPerSample) / 8, true);
    view.setUint16(34, bitsPerSample, true);

    // "data"
    u8[36] = 0x64;
    u8[37] = 0x61;
    u8[38] = 0x74;
    u8[39] = 0x61;
    view.setUint32(40, dataSize, true);

    u8.set(samples, 44);
    return buffer;
}

function makeWavBlob(samples: Uint8Array, sampleRate = 16000): Blob {
    return new Blob([makeWavBuffer(samples, sampleRate)], {
        type: 'audio/wav',
    });
}

describe('concatWavBlobs', () => {
    it('単一の Blob はそのまま返す', async () => {
        const blob = makeWavBlob(new Uint8Array([1, 2, 3, 4]));
        const result = await concatWavBlobs([blob]);
        expect(result).toBe(blob);
    });

    it('空配列はエラー', async () => {
        await expect(concatWavBlobs([])).rejects.toThrow();
    });

    it('2 つの WAV を結合し RIFF/data サイズを正しく更新する', async () => {
        const a = makeWavBlob(new Uint8Array([1, 2, 3, 4]));
        const b = makeWavBlob(new Uint8Array([5, 6, 7, 8]));
        const result = await concatWavBlobs([a, b]);

        const buf = await result.arrayBuffer();
        const view = new DataView(buf);

        const riffId = String.fromCharCode(
            view.getUint8(0),
            view.getUint8(1),
            view.getUint8(2),
            view.getUint8(3),
        );
        expect(riffId).toBe('RIFF');

        const waveId = String.fromCharCode(
            view.getUint8(8),
            view.getUint8(9),
            view.getUint8(10),
            view.getUint8(11),
        );
        expect(waveId).toBe('WAVE');

        // RIFF size = total - 8
        expect(view.getUint32(4, true)).toBe(buf.byteLength - 8);

        // data chunk size = 4 + 4 = 8
        expect(view.getUint32(40, true)).toBe(8);

        const data = new Uint8Array(buf, 44, 8);
        expect(Array.from(data)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    });

    it('RIFF ヘッダが無い Blob はエラー', async () => {
        const bogus = new Blob([new Uint8Array(50)], { type: 'audio/wav' });
        await expect(concatWavBlobs([bogus, bogus])).rejects.toThrow(
            /RIFF\/WAVE/,
        );
    });

    it('silenceSeconds 指定時に無音 PCM バイトが間に挿入される', async () => {
        // 16-bit mono, 16000 Hz の場合: blockAlign = 2 → 0.5 秒 = 16000 bytes
        const a = makeWavBlob(new Uint8Array([1, 2, 3, 4]), 16000);
        const b = makeWavBlob(new Uint8Array([5, 6, 7, 8]), 16000);
        const result = await concatWavBlobs([a, b], 0.5);

        const buf = await result.arrayBuffer();
        const view = new DataView(buf);

        // data chunk size = 4 (a) + 16000 (silence) + 4 (b) = 16008
        expect(view.getUint32(40, true)).toBe(16008);

        const data = new Uint8Array(buf, 44, 16008);
        // 先頭 4 バイトが a の data
        expect(Array.from(data.slice(0, 4))).toEqual([1, 2, 3, 4]);
        // 末尾 4 バイトが b の data
        expect(Array.from(data.slice(16004, 16008))).toEqual([5, 6, 7, 8]);
        // 間の 16000 バイトはすべて 0（無音）
        for (let i = 4; i < 16004; i++) {
            if (data[i] !== 0) {
                throw new Error(`silence byte at ${i} is not 0: ${data[i]}`);
            }
        }
    });

    it('silenceSeconds=0 はサイズが増えない（後方互換）', async () => {
        const a = makeWavBlob(new Uint8Array([1, 2, 3, 4]));
        const b = makeWavBlob(new Uint8Array([5, 6, 7, 8]));
        const withZero = await concatWavBlobs([a, b], 0);
        const withoutArg = await concatWavBlobs([a, b]);
        expect(withZero.size).toBe(withoutArg.size);
    });
});

describe('formatTimestampForFilename', () => {
    it('YYYYMMDD-HHmmss 形式で 0 埋めする', () => {
        const d = new Date(2026, 3, 5, 9, 7, 3);
        expect(formatTimestampForFilename(d)).toBe('20260405-090703');
    });

    it('2 桁の月日時分秒もそのまま', () => {
        const d = new Date(2026, 11, 25, 23, 59, 59);
        expect(formatTimestampForFilename(d)).toBe('20261225-235959');
    });
});
