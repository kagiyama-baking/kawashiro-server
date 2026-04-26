import { fetchAudioBlob } from '@/lib/api/talk';
import type { ChatSessionMessage } from '@/types/talk';

export interface FetchedAudio {
    readonly blob: Blob;
    readonly format: string;
}

export function countPlayableAudios(
    messages: readonly ChatSessionMessage[],
): number {
    return messages.filter(
        (m) => m.audio_url !== null && m.audio_size_bytes > 0,
    ).length;
}

export async function loadSessionAudios(
    sessionId: string,
    messages: readonly ChatSessionMessage[],
): Promise<FetchedAudio[]> {
    const targets = messages.filter(
        (m) => m.audio_url !== null && m.audio_size_bytes > 0,
    );
    return Promise.all(
        targets.map(async (m) => ({
            blob: await fetchAudioBlob(sessionId, m.id),
            format: m.audio_format || 'wav',
        })),
    );
}

export function isAllWav(audios: readonly FetchedAudio[]): boolean {
    return audios.length > 0 && audios.every((a) => a.format === 'wav');
}
