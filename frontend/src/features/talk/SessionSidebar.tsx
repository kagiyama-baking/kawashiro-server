import { Loader2, Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { ChatSessionListItem } from '@/types/talk';
import { SessionListItem } from './SessionListItem';

interface SessionSidebarProps {
    readonly sessions: ChatSessionListItem[];
    readonly activeSessionId: string | null;
    readonly hasMore: boolean;
    readonly isLoading: boolean;
    readonly onSelect: (id: string) => void;
    readonly onDelete: (id: string) => void;
    readonly onLoadMore: () => void;
    readonly onNew: () => void;
    // モバイルドロワー制御
    readonly isOpen: boolean;
    readonly onClose: () => void;
}

export function SessionSidebar({
    sessions,
    activeSessionId,
    hasMore,
    isLoading,
    onSelect,
    onDelete,
    onLoadMore,
    onNew,
    isOpen,
    onClose,
}: SessionSidebarProps) {
    const handleSelect = (id: string) => {
        onSelect(id);
        onClose(); // モバイル時に閉じる（デスクトップでは onClose は no-op）
    };

    return (
        <>
            {/* モバイル用 overlay */}
            <div
                className={cn(
                    'bg-overlay fixed inset-0 z-40 backdrop-blur-[4px] md:hidden',
                    isOpen ? 'block' : 'hidden',
                )}
                onClick={onClose}
                role="presentation"
            />

            <aside
                className={cn(
                    'bg-background fixed top-0 left-0 z-50 flex h-full w-72 flex-col border-r transition-transform',
                    'md:relative md:z-0 md:h-auto md:w-72 md:translate-x-0',
                    isOpen
                        ? 'translate-x-0'
                        : '-translate-x-full md:translate-x-0',
                )}
            >
                <div className="flex items-center justify-between border-b px-3 py-3">
                    <h2 className="text-sm">チャット履歴</h2>
                    <div className="flex items-center gap-1">
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={onNew}
                        >
                            <Plus />
                            新規
                        </Button>
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon-sm"
                            className="md:hidden"
                            onClick={onClose}
                            aria-label="閉じる"
                        >
                            <X className="h-4 w-4" />
                        </Button>
                    </div>
                </div>

                <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-2">
                    {sessions.length === 0 && !isLoading && (
                        <div className="text-muted-foreground p-4 text-center text-xs">
                            まだ履歴がありません
                        </div>
                    )}
                    {sessions.map((s) => (
                        <SessionListItem
                            key={s.id}
                            item={s}
                            isActive={s.id === activeSessionId}
                            onSelect={handleSelect}
                            onDelete={onDelete}
                        />
                    ))}
                    {hasMore && (
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={onLoadMore}
                            disabled={isLoading}
                            className="mt-2 w-full"
                        >
                            {isLoading ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                                'もっと読み込む'
                            )}
                        </Button>
                    )}
                </div>
            </aside>
        </>
    );
}
