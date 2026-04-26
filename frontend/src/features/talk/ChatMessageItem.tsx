import { Check, Pencil, Trash2, Volume2, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { AudioDownload } from '@/components/audio/AudioDownload';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { fetchAudioBlob } from '@/lib/api/talk';
import { formatBytes } from '@/lib/format/bytes';
import { cn } from '@/lib/utils';
import { useChatStore } from '@/stores/chat-store';
import { CHAT_MESSAGE_MAX_LENGTH, type ChatSessionMessage } from '@/types/talk';

interface ChatMessageItemProps {
    readonly sessionId: string;
    readonly message: ChatSessionMessage;
    readonly disabled: boolean;
    readonly onEdit: (msgId: number, newContent: string) => void;
}

export function ChatMessageItem({
    sessionId,
    message,
    disabled,
    onEdit,
}: ChatMessageItemProps) {
    const isUser = message.role === 'user';
    const ensureAudioObjectUrl = useChatStore((s) => s.ensureAudioObjectUrl);
    const cachedUrl = useChatStore((s) => s.audioObjectUrls.get(message.id));
    const deleteMessageAudio = useChatStore((s) => s.deleteMessageAudio);

    // ChatThreadView 側で key={message.id} を指定しているため
    // メッセージ切替時にコンポーネントが再マウントされ初期値が更新される
    const [isEditing, setIsEditing] = useState(false);
    const [draft, setDraft] = useState(message.content);
    const [downloadBlob, setDownloadBlob] = useState<Blob | null>(null);
    const [audioError, setAudioError] = useState<string | null>(null);

    useEffect(() => {
        if (!message.audio_url) return;
        let cancelled = false;
        fetchAudioBlob(sessionId, message.id)
            .then((blob) => {
                if (!cancelled) setDownloadBlob(blob);
            })
            .catch(() => {
                if (!cancelled) setAudioError('音声の取得に失敗しました');
            });
        ensureAudioObjectUrl(message.id).catch(() => {
            if (!cancelled) setAudioError('音声の取得に失敗しました');
        });
        return () => {
            cancelled = true;
        };
    }, [sessionId, message.id, message.audio_url, ensureAudioObjectUrl]);

    const draftTrimmed = draft.trim();
    const isOverLimit = draft.length > CHAT_MESSAGE_MAX_LENGTH;
    const isUnchanged = draftTrimmed === message.content.trim();
    const cannotSave = draftTrimmed === '' || isOverLimit;

    const startEdit = () => {
        setDraft(message.content);
        setIsEditing(true);
    };
    const cancelEdit = () => {
        setDraft(message.content);
        setIsEditing(false);
    };
    const saveEdit = () => {
        if (cannotSave) return;
        setIsEditing(false);
        if (isUnchanged) return;
        onEdit(message.id, draft);
    };

    const handleDeleteAudio = async () => {
        if (!confirm('この音声を削除しますか？')) return;
        await deleteMessageAudio(message.id);
        setDownloadBlob(null);
    };

    const filename = `chat-${message.sequence + 1}.${message.audio_format || 'wav'}`;

    return (
        <div
            className={cn(
                'animate-slide-up flex w-full',
                isUser ? 'justify-end' : 'justify-start',
            )}
        >
            <div
                className={cn(
                    'flex max-w-[85%] flex-col gap-2',
                    isUser ? 'items-end' : 'items-start',
                )}
            >
                {isEditing ? (
                    <div className="flex w-full flex-col gap-2 sm:w-[420px]">
                        <Textarea
                            value={draft}
                            onChange={(e) => setDraft(e.target.value)}
                            rows={3}
                            aria-invalid={isOverLimit || undefined}
                        />
                        <div className="text-muted-foreground flex items-center justify-between text-[12px]">
                            <span>
                                編集して再送すると以降の履歴は破棄されます
                            </span>
                            <span
                                className={
                                    isOverLimit
                                        ? 'text-destructive font-medium'
                                        : undefined
                                }
                            >
                                {draft.length} / {CHAT_MESSAGE_MAX_LENGTH}
                            </span>
                        </div>
                        <div className="flex justify-end gap-2">
                            <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                onClick={cancelEdit}
                            >
                                <X className="mr-1 h-3.5 w-3.5" />
                                キャンセル
                            </Button>
                            <Button
                                type="button"
                                size="sm"
                                onClick={saveEdit}
                                disabled={cannotSave}
                            >
                                <Check className="mr-1 h-3.5 w-3.5" />
                                保存して再送
                            </Button>
                        </div>
                    </div>
                ) : (
                    <>
                        <div
                            className={cn(
                                'rounded-2xl px-4 py-2.5 text-[13px] leading-relaxed whitespace-pre-wrap',
                                isUser
                                    ? 'text-foreground bg-[oklch(0.75_0.20_155/0.18)]'
                                    : 'glass text-foreground',
                            )}
                        >
                            {message.content}
                        </div>

                        {isUser && (
                            <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                onClick={startEdit}
                                disabled={disabled}
                                className="text-muted-foreground h-7 px-2 text-[12px]"
                            >
                                <Pencil className="mr-1 h-3 w-3" />
                                編集
                            </Button>
                        )}

                        {message.audio_url && cachedUrl && (
                            <div className="flex w-full flex-col gap-2 sm:w-[420px]">
                                <AudioPlayer src={cachedUrl} />
                                <div className="flex items-center justify-between gap-2">
                                    <span className="text-muted-foreground inline-flex items-center gap-1 text-[11px]">
                                        <Volume2 className="h-3 w-3" />
                                        {formatBytes(message.audio_size_bytes)}
                                    </span>
                                    <div className="flex items-center gap-1">
                                        <AudioDownload
                                            blob={downloadBlob}
                                            filename={filename}
                                        />
                                        <Button
                                            type="button"
                                            size="sm"
                                            variant="ghost"
                                            onClick={handleDeleteAudio}
                                            disabled={disabled}
                                            className="text-muted-foreground h-7 px-2 text-[12px]"
                                            aria-label="音声を削除"
                                        >
                                            <Trash2 className="h-3.5 w-3.5" />
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        )}
                        {audioError && (
                            <span className="text-destructive text-[12px]">
                                {audioError}
                            </span>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}
