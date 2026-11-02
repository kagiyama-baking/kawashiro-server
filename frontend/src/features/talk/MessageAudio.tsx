import { useAuiState } from '@assistant-ui/react';
import { Loader2, Trash2, Volume2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { AudioDownload } from '@/components/audio/AudioDownload';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { Button } from '@/components/ui/button';
import { formatBytes } from '@/lib/format/bytes';
import { useChatStore } from '@/stores/chat-store';
import type { ChatMessageCustom } from './useChatRuntime';

interface SavedAudioProps {
    readonly messageId: number;
    readonly filename: string;
    readonly sizeBytes: number;
}

function SavedAudio({ messageId, filename, sizeBytes }: SavedAudioProps) {
    const ensureAudioObjectUrl = useChatStore((s) => s.ensureAudioObjectUrl);
    const deleteMessageAudio = useChatStore((s) => s.deleteMessageAudio);
    const objectUrl = useChatStore((s) => s.audioObjectUrls.get(messageId));
    const blob = useChatStore((s) => s.audioBlobs.get(messageId));
    const [error, setError] = useState<string | null>(null);
    const [isConfirmingDelete, setIsConfirmingDelete] = useState(false);

    useEffect(() => {
        let cancelled = false;
        // ストアが Blob と Object URL を 1 度だけ取得してキャッシュする
        ensureAudioObjectUrl(messageId).catch(() => {
            if (!cancelled) setError('音声の取得に失敗しました');
        });
        return () => {
            cancelled = true;
        };
    }, [messageId, ensureAudioObjectUrl]);

    const handleConfirmDelete = async () => {
        setIsConfirmingDelete(false);
        await deleteMessageAudio(messageId);
    };

    return (
        <div className="mt-2 flex w-full max-w-md flex-col gap-2">
            {objectUrl && <AudioPlayer src={objectUrl} />}
            {!objectUrl && !error && (
                <p className="text-muted-foreground bg-secondary rounded-lg border p-3 text-xs">
                    音声を読み込み中…
                </p>
            )}
            {error && <p className="text-destructive text-xs">{error}</p>}
            <div className="flex items-center justify-between gap-2">
                <span className="text-ink-subtle font-latin inline-flex items-center gap-1 text-xs">
                    <Volume2 className="size-3" />
                    {formatBytes(sizeBytes)}
                </span>
                <div className="flex items-center gap-1">
                    <AudioDownload blob={blob ?? null} filename={filename} />
                    <Button
                        type="button"
                        size="icon-sm"
                        variant="ghost"
                        onClick={() => setIsConfirmingDelete(true)}
                        aria-label="音声を削除"
                    >
                        <Trash2 />
                    </Button>
                </div>
            </div>
            <ConfirmDialog
                open={isConfirmingDelete}
                title="音声を削除"
                confirmLabel="削除"
                destructive
                onConfirm={handleConfirmDelete}
                onCancel={() => setIsConfirmingDelete(false)}
            >
                この音声を削除しますか？
            </ConfirmDialog>
        </div>
    );
}

/** 応答の音声。合成の状態と、保存された音声の再生・保存・削除を出す。 */
export function MessageAudio() {
    // 応答が届くまでの上流の仮の行には custom の中身がない
    const custom = useAuiState(
        (s) => s.message.metadata.custom,
    ) as Partial<ChatMessageCustom>;

    if (custom.audioState === 'pending') {
        return (
            <p className="text-ink-subtle mt-2 flex items-center gap-2 text-xs">
                <Loader2 className="size-3 animate-spin" />
                音声を合成中…
            </p>
        );
    }
    if (custom.audioState === 'failed') {
        return (
            <p className="text-destructive mt-2 text-xs">
                {custom.audioError ?? '音声の合成に失敗しました'}
            </p>
        );
    }
    if (!custom.audio_url || typeof custom.serverId !== 'number') return null;

    const sequence = (custom.sequence ?? 0) + 1;
    return (
        <SavedAudio
            messageId={custom.serverId}
            filename={`chat-${sequence}.${custom.audio_format || 'wav'}`}
            sizeBytes={custom.audio_size_bytes ?? 0}
        />
    );
}
