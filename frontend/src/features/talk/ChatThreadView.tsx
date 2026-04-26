import { Loader2, MessagesSquare, Trash2 } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { ErrorMessage } from '@/components/common/ErrorMessage';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { useChatStore } from '@/stores/chat-store';
import { AudioBundleDownload } from './AudioBundleDownload';
import { AudioBundlePlay } from './AudioBundlePlay';
import { ChatInputForm } from './ChatInputForm';
import { ChatMessageItem } from './ChatMessageItem';
import { SessionTitleEditor } from './SessionTitleEditor';

export function ChatThreadView() {
    const session = useChatStore((s) => s.activeSession);
    const isLoadingDetail = useChatStore((s) => s.isLoadingDetail);
    const isSendingMessage = useChatStore((s) => s.isSendingMessage);
    const error = useChatStore((s) => s.error);
    const sendMessage = useChatStore((s) => s.sendMessage);
    const editAndResend = useChatStore((s) => s.editAndResend);
    const cancelMessage = useChatStore((s) => s.cancelMessage);
    const updateActiveTitle = useChatStore((s) => s.updateActiveTitle);
    const deleteAllAudio = useChatStore((s) => s.deleteAllAudio);

    const [input, setInput] = useState('');
    const bottomRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }, [session?.messages.length, isSendingMessage]);

    if (isLoadingDetail) {
        return (
            <div className="flex h-full items-center justify-center">
                <Loader2 className="text-muted-foreground h-6 w-6 animate-spin" />
            </div>
        );
    }

    if (!session) {
        return (
            <div className="text-muted-foreground flex h-full flex-col items-center justify-center gap-3">
                <MessagesSquare className="h-10 w-10 opacity-30" />
                <p className="text-[13px]">
                    左のサイドバーからチャットを選択するか、新規作成してください
                </p>
            </div>
        );
    }

    const handleSubmit = async () => {
        const text = input;
        setInput('');
        await sendMessage(text);
    };

    const handleBulkDeleteAudio = async () => {
        if (
            !confirm(
                'このセッションの音声ファイルを全て削除します。よろしいですか？',
            )
        )
            return;
        await deleteAllAudio();
    };

    return (
        <div className="flex h-full flex-col">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[oklch(0.95_0_0/0.06)] px-4 py-3">
                <SessionTitleEditor
                    title={session.title}
                    onSave={updateActiveTitle}
                />
                <div className="flex items-center gap-2">
                    <AudioBundlePlay
                        sessionId={session.id}
                        messages={session.messages}
                        disabled={isSendingMessage}
                    />
                    <AudioBundleDownload
                        sessionId={session.id}
                        messages={session.messages}
                        disabled={isSendingMessage}
                    />
                    <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={handleBulkDeleteAudio}
                        disabled={
                            isSendingMessage ||
                            session.messages.every((m) => !m.audio_url)
                        }
                    >
                        <Trash2 className="mr-1 h-4 w-4" />
                        音声を全削除
                    </Button>
                </div>
            </div>

            <Separator className="opacity-30" />

            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
                {session.messages.length === 0 && !isSendingMessage && (
                    <div className="text-muted-foreground flex h-[40vh] flex-col items-center justify-center gap-2">
                        <MessagesSquare className="h-8 w-8 opacity-30" />
                        <p className="text-[13px]">
                            メッセージを送信してチャットを始めましょう
                        </p>
                    </div>
                )}
                {session.messages.map((m) => (
                    <ChatMessageItem
                        key={m.id}
                        message={m}
                        disabled={isSendingMessage}
                        onEdit={editAndResend}
                    />
                ))}
                {isSendingMessage && (
                    <div className="text-muted-foreground flex items-center gap-2 text-[12px]">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span>応答を生成中...</span>
                    </div>
                )}
                <div ref={bottomRef} />
            </div>

            <div className="border-t border-[oklch(0.95_0_0/0.06)] p-4">
                <ChatInputForm
                    input={input}
                    onInputChange={setInput}
                    onSubmit={handleSubmit}
                    onCancel={cancelMessage}
                    isLoading={isSendingMessage}
                />
                <ErrorMessage message={error} />
            </div>
        </div>
    );
}
