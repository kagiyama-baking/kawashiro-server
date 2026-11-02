import {
    ActionBarPrimitive,
    AuiIf,
    ComposerPrimitive,
    type EmptyMessagePartComponent,
    MessagePrimitive,
    type TextMessagePartComponent,
    ThreadPrimitive,
    useAuiState,
} from '@assistant-ui/react';
import {
    ArrowDown,
    ArrowUp,
    Check,
    Copy,
    Loader2,
    Pencil,
    RefreshCw,
    Square,
} from 'lucide-react';
import type { FormEvent, KeyboardEvent } from 'react';
import { MarkdownText } from '@/components/assistant-ui/elements/markdown-text';
import { TooltipIconButton } from '@/components/assistant-ui/elements/tooltip-icon-button';
import { PageHeader } from '@/components/common/PageHeader';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { selectHasLoadFailed, useChatStore } from '@/stores/chat-store';
import { CHAT_MESSAGE_MAX_LENGTH } from '@/types/talk';
import { ChatHeader } from './ChatHeader';
import { ChatNotices } from './ChatNotices';
import { MessageAudio } from './MessageAudio';
import { PresetPicker } from './PresetPicker';

// マウスがある環境では、最後の行以外のアクションは行に乗せたときだけ出す。
// タッチの環境とキーボード操作では常に届くようにする。
const REVEAL_ON_HOVER =
    '[@media(hover:hover)]:opacity-0 [@media(hover:hover)]:transition-opacity [@media(hover:hover)]:group-hover/message:opacity-100 [@media(hover:hover)]:focus-within:opacity-100';

/** タッチの環境で自動フォーカスすると、開いただけでソフトキーボードが画面を覆ってしまう。 */
function canAutoFocusComposer(): boolean {
    return window.matchMedia?.('(hover: hover)').matches ?? false;
}

function useComposerLimit() {
    const length = useAuiState((s) => s.composer.text.length);
    return { length, isOverLimit: length > CHAT_MESSAGE_MAX_LENGTH };
}

function CharacterCount() {
    const { length, isOverLimit } = useComposerLimit();
    return (
        <span
            className={cn(
                'font-latin text-ink-subtle text-xs tabular-nums',
                isOverLimit && 'text-destructive font-medium',
            )}
        >
            {length} / {CHAT_MESSAGE_MAX_LENGTH}
        </span>
    );
}

function Composer({ isEmpty }: { readonly isEmpty: boolean }) {
    const { isOverLimit } = useComposerLimit();
    const isRunning = useAuiState((s) => s.thread.isRunning);

    // 文字数の超過は Enter でも止める。maxLength は貼り付けを黙って切るので使わない
    const handleSubmit = (e: FormEvent) => {
        if (isOverLimit) e.preventDefault();
    };

    // 生成中の Enter で意図しない改行が入らないようにする。IME の確定は対象にしない
    const handleKeyDown = (e: KeyboardEvent) => {
        if (
            isRunning &&
            e.key === 'Enter' &&
            !e.shiftKey &&
            !e.nativeEvent.isComposing &&
            e.keyCode !== 229
        ) {
            e.preventDefault();
        }
    };

    return (
        <ComposerPrimitive.Root
            onSubmit={handleSubmit}
            className="bg-card border-input shadow-lift focus-within:border-ring focus-within:ring-ring/22 flex w-full cursor-text flex-col gap-1 rounded-[1.25rem] border p-2 transition-[border-color,box-shadow] duration-250 focus-within:ring-3"
        >
            <ComposerPrimitive.Input
                aria-label="メッセージ"
                placeholder={
                    isEmpty ? 'メッセージを入力' : '続けてメッセージを入力'
                }
                rows={1}
                autoFocus={canAutoFocusComposer()}
                enterKeyHint="send"
                onKeyDown={handleKeyDown}
                className="text-ink-strong placeholder:text-ink-subtle max-h-48 min-h-10 w-full resize-none bg-transparent px-2.5 py-1.5 outline-none"
            />
            <div className="flex items-center justify-between gap-3 pl-2.5">
                <div className="flex min-w-0 items-center gap-3">
                    <CharacterCount />
                    <span className="text-ink-subtle hidden text-xs [@media(hover:hover)]:sm:inline">
                        Enter で送信、Shift+Enter で改行
                    </span>
                </div>
                <AuiIf condition={(s) => !s.thread.isRunning}>
                    <ComposerPrimitive.Send asChild disabled={isOverLimit}>
                        <Button
                            size="icon"
                            className="rounded-full"
                            aria-label="送信"
                        >
                            <ArrowUp className="size-5" />
                        </Button>
                    </ComposerPrimitive.Send>
                </AuiIf>
                <AuiIf condition={(s) => s.thread.isRunning}>
                    <ComposerPrimitive.Cancel asChild>
                        <Button
                            size="icon"
                            className="rounded-full"
                            aria-label="停止"
                        >
                            <Square className="size-3.5 fill-current" />
                        </Button>
                    </ComposerPrimitive.Cancel>
                </AuiIf>
            </div>
        </ComposerPrimitive.Root>
    );
}

const UserText: TextMessagePartComponent = ({ text }) => (
    <span className="whitespace-pre-wrap">{text}</span>
);

const USER_PARTS = { Text: UserText };

const Thinking: EmptyMessagePartComponent = ({ status }) =>
    status.type === 'running' ? (
        <span className="text-ink-subtle animate-pulse text-sm">
            考えています…
        </span>
    ) : null;

const ASSISTANT_PARTS = { Text: MarkdownText, Empty: Thinking };

function UserMessage() {
    const isSyncing = useChatStore((s) => s.isSyncing);

    return (
        <MessagePrimitive.Root className="group/message flex flex-col items-end gap-1">
            <div className="bg-card text-foreground max-w-[85%] rounded-lg border px-4 py-2.5 wrap-anywhere">
                <MessagePrimitive.Parts components={USER_PARTS} />
            </div>
            <div className="flex min-h-[30px] items-center">
                {!isSyncing && (
                    <ActionBarPrimitive.Root
                        hideWhenRunning
                        className={REVEAL_ON_HOVER}
                    >
                        <ActionBarPrimitive.Edit asChild>
                            <TooltipIconButton tooltip="編集">
                                <Pencil />
                            </TooltipIconButton>
                        </ActionBarPrimitive.Edit>
                    </ActionBarPrimitive.Root>
                )}
            </div>
        </MessagePrimitive.Root>
    );
}

function AssistantMessage() {
    const isSyncing = useChatStore((s) => s.isSyncing);
    const isLast = useAuiState((s) => s.message.isLast);

    return (
        <MessagePrimitive.Root className="group/message flex min-w-0 flex-col gap-1">
            <div className="min-w-0 wrap-anywhere">
                <MessagePrimitive.Parts components={ASSISTANT_PARTS} />
            </div>
            <AuiIf
                condition={(s) =>
                    s.message.status?.type === 'incomplete' &&
                    s.message.status.reason === 'cancelled'
                }
            >
                <p className="text-ink-subtle text-xs">ここで停止しました</p>
            </AuiIf>
            <MessageAudio />
            <div className="-ml-2 flex min-h-[30px] items-center">
                {!isSyncing && (
                    <ActionBarPrimitive.Root
                        hideWhenRunning
                        className={cn(
                            'flex items-center gap-0.5',
                            !isLast && REVEAL_ON_HOVER,
                        )}
                    >
                        <ActionBarPrimitive.Copy asChild>
                            <TooltipIconButton tooltip="コピー">
                                <AuiIf condition={(s) => s.message.isCopied}>
                                    <Check />
                                </AuiIf>
                                <AuiIf condition={(s) => !s.message.isCopied}>
                                    <Copy />
                                </AuiIf>
                            </TooltipIconButton>
                        </ActionBarPrimitive.Copy>
                        {/* 古い応答の再生成は以降の履歴を黙って消すので、最後の応答にだけ出す */}
                        {isLast && (
                            <ActionBarPrimitive.Reload asChild>
                                <TooltipIconButton tooltip="再生成">
                                    <RefreshCw />
                                </TooltipIconButton>
                            </ActionBarPrimitive.Reload>
                        )}
                    </ActionBarPrimitive.Root>
                )}
            </div>
        </MessagePrimitive.Root>
    );
}

function EditComposer() {
    const { isOverLimit } = useComposerLimit();
    const isSyncing = useChatStore((s) => s.isSyncing);
    const isUnchanged = useAuiState((s) => {
        const original = s.message.content
            .flatMap((part) => (part.type === 'text' ? [part.text] : []))
            .join('');
        return s.composer.text.trim() === original.trim();
    });
    const cannotSend = isOverLimit || isUnchanged || isSyncing;

    const handleSubmit = (e: FormEvent) => {
        if (cannotSend) e.preventDefault();
    };

    return (
        <MessagePrimitive.Root className="flex justify-end pb-[calc(30px+0.25rem)]">
            <ComposerPrimitive.Root
                onSubmit={handleSubmit}
                className="bg-card border-input focus-within:border-ring flex w-full max-w-[85%] flex-col gap-2 rounded-lg border p-3 transition-[border-color] duration-250"
            >
                <ComposerPrimitive.Input
                    aria-label="メッセージを編集"
                    autoFocus
                    className="text-ink-strong max-h-64 min-h-14 w-full resize-none bg-transparent outline-none"
                />
                <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
                    <p className="text-ink-subtle text-xs">
                        送信すると、これ以降の履歴は置き換わります
                    </p>
                    <CharacterCount />
                </div>
                <div className="flex justify-end gap-2">
                    <ComposerPrimitive.Cancel asChild>
                        <Button variant="ghost" size="sm">
                            キャンセル
                        </Button>
                    </ComposerPrimitive.Cancel>
                    <ComposerPrimitive.Send asChild disabled={cannotSend}>
                        <Button size="sm">送信して置き換える</Button>
                    </ComposerPrimitive.Send>
                </div>
            </ComposerPrimitive.Root>
        </MessagePrimitive.Root>
    );
}

function ThreadMessage() {
    const role = useAuiState((s) => s.message.role);
    const isEditing = useAuiState((s) => s.message.composer.isEditing);

    if (isEditing) return <EditComposer />;
    return role === 'user' ? <UserMessage /> : <AssistantMessage />;
}

function ScrollToBottom() {
    return (
        <ThreadPrimitive.ScrollToBottom asChild>
            <Button
                variant="outline"
                size="icon"
                aria-label="いちばん下へ"
                className="shadow-lift absolute -top-11 left-1/2 -translate-x-1/2 rounded-full disabled:invisible"
            >
                <ArrowDown />
            </Button>
        </ThreadPrimitive.ScrollToBottom>
    );
}

function Welcome() {
    return (
        <div className="mb-5 flex flex-col items-center gap-1 text-center">
            <PageHeader eyebrow="TALK" title="何を話しましょうか" />
            <PresetPicker />
        </div>
    );
}

/** チャットの本体。配置は ChatGPT に倣い、色と部品はテーマのトークンを使う。 */
export function ChatThread() {
    const hasNoMessages = useAuiState((s) => s.thread.messages.length === 0);
    const isThreadLoading = useAuiState((s) => s.thread.isLoading);
    // 読み込みに失敗したチャットは、新規チャットに見せない
    const hasLoadFailed = useChatStore(selectHasLoadFailed);
    const isEmpty = hasNoMessages && !isThreadLoading && !hasLoadFailed;
    const isLoading = hasNoMessages && isThreadLoading;

    return (
        <ThreadPrimitive.Root className="flex h-full min-h-0 flex-col">
            {!isEmpty && <h1 className="sr-only">チャット</h1>}
            <ChatHeader />
            <ThreadPrimitive.Viewport className="flex min-h-0 flex-1 flex-col overflow-x-hidden overflow-y-auto">
                <div
                    className={cn(
                        'mx-auto flex w-full max-w-3xl flex-1 flex-col px-4',
                        isEmpty && 'justify-center',
                    )}
                >
                    {isEmpty && <Welcome />}
                    {isLoading && (
                        <div
                            role="status"
                            aria-label="読み込み中"
                            className="flex flex-1 items-center justify-center"
                        >
                            <Loader2 className="text-muted-foreground size-6 animate-spin" />
                        </div>
                    )}
                    <div className="flex flex-col gap-2 pt-6 empty:hidden">
                        <ThreadPrimitive.Messages>
                            {() => <ThreadMessage />}
                        </ThreadPrimitive.Messages>
                    </div>
                    <ThreadPrimitive.ViewportFooter
                        className={cn(
                            'bg-background relative pt-2 pb-4',
                            !isEmpty && 'sticky bottom-0 mt-auto',
                        )}
                    >
                        <ScrollToBottom />
                        <ChatNotices />
                        <Composer isEmpty={isEmpty} />
                    </ThreadPrimitive.ViewportFooter>
                </div>
            </ThreadPrimitive.Viewport>
        </ThreadPrimitive.Root>
    );
}
