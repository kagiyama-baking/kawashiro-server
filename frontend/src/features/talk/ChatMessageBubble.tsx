import { AlertCircle, Check, Pencil, X } from 'lucide-react';
import { useState } from 'react';
import { AudioDownload } from '@/components/audio/AudioDownload';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { CHAT_MESSAGE_MAX_LENGTH, type ChatMessageResult } from '@/types/talk';

interface ChatMessageBubbleProps {
    readonly message: ChatMessageResult;
    readonly index: number;
    readonly isEditable: boolean;
    readonly disabled: boolean;
    readonly onEdit?: (messageId: string, newContent: string) => void;
}

export function ChatMessageBubble({
    message,
    index,
    isEditable,
    disabled,
    onEdit,
}: ChatMessageBubbleProps) {
    const isUser = message.role === 'user';
    const filename = `chat-${index + 1}.${message.audioFormat ?? 'wav'}`;

    const [isEditing, setIsEditing] = useState(false);
    const [draft, setDraft] = useState(message.content);

    const draftLength = draft.length;
    const draftTrimmed = draft.trim();
    const isOverLimit = draftLength > CHAT_MESSAGE_MAX_LENGTH;
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
        if (cannotSave || !onEdit) return;
        setIsEditing(false);
        if (isUnchanged) return;
        onEdit(message.id, draft);
    };

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
                                {draftLength} / {CHAT_MESSAGE_MAX_LENGTH}
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

                        {isEditable && onEdit && (
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

                        {message.audioUrl && (
                            <div className="flex w-full flex-col gap-2 sm:w-[420px]">
                                <AudioPlayer src={message.audioUrl} />
                                <div>
                                    <AudioDownload
                                        blob={message.audioBlob}
                                        filename={filename}
                                    />
                                </div>
                            </div>
                        )}

                        {message.errorMessage && (
                            <div className="text-destructive flex items-center gap-1.5 text-[12px]">
                                <AlertCircle className="h-3.5 w-3.5" />
                                <span>{message.errorMessage}</span>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}
