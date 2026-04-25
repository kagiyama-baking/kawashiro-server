import { MessagesSquare } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { Loader2 } from 'lucide-react';
import type { ChatMessageResult } from '@/types/talk';
import { ChatMessageBubble } from './ChatMessageBubble';

interface ChatMessageListProps {
    readonly messages: ChatMessageResult[];
    readonly isLoading: boolean;
}

export function ChatMessageList({ messages, isLoading }: ChatMessageListProps) {
    const bottomRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }, [messages.length, isLoading]);

    if (messages.length === 0 && !isLoading) {
        return (
            <div className="text-muted-foreground flex h-[420px] flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-[oklch(0.95_0_0/0.08)]">
                <MessagesSquare className="h-8 w-8 opacity-40" />
                <p className="text-[13px]">
                    プリセットを選んでメッセージを送信すると、会話が始まります
                </p>
            </div>
        );
    }

    return (
        <div className="max-h-[60vh] min-h-[320px] space-y-4 overflow-y-auto rounded-xl border border-[oklch(0.95_0_0/0.06)] p-4">
            {messages.map((message, index) => (
                <ChatMessageBubble
                    key={message.id}
                    message={message}
                    index={index}
                />
            ))}
            {isLoading && (
                <div className="text-muted-foreground flex items-center gap-2 text-[12px]">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    <span>応答を生成中...</span>
                </div>
            )}
            <div ref={bottomRef} />
        </div>
    );
}
