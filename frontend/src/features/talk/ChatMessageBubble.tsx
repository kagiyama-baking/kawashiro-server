import { AlertCircle } from 'lucide-react';
import { AudioDownload } from '@/components/audio/AudioDownload';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import { cn } from '@/lib/utils';
import type { ChatMessageResult } from '@/types/talk';

interface ChatMessageBubbleProps {
    readonly message: ChatMessageResult;
    readonly index: number;
}

export function ChatMessageBubble({ message, index }: ChatMessageBubbleProps) {
    const isUser = message.role === 'user';
    const filename = `chat-${index + 1}.${message.audioFormat ?? 'wav'}`;

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
            </div>
        </div>
    );
}
