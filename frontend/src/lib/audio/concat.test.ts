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
