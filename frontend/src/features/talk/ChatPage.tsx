import { Menu } from 'lucide-react';
import { useEffect, useState } from 'react';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { Button } from '@/components/ui/button';
import { fetchConfigs } from '@/lib/api/talk';
import { useChatStore } from '@/stores/chat-store';
import type { GenerateConfig } from '@/types/talk';
import { ChatThreadView } from './ChatThreadView';
import { NewSessionDialog } from './NewSessionDialog';
import { SessionSidebar } from './SessionSidebar';

export function ChatPage() {
    const sessions = useChatStore((s) => s.sessions);
    const activeSessionId = useChatStore((s) => s.activeSessionId);
    const hasMore = useChatStore((s) => s.hasMoreSessions);
    const isLoadingList = useChatStore((s) => s.isLoadingList);
    const loadSessions = useChatStore((s) => s.loadSessions);
    const loadMoreSessions = useChatStore((s) => s.loadMoreSessions);
    const selectSession = useChatStore((s) => s.selectSession);
    const removeSession = useChatStore((s) => s.removeSession);
    const createNewSession = useChatStore((s) => s.createNewSession);
    const reset = useChatStore((s) => s.reset);

    const [configs, setConfigs] = useState<GenerateConfig[]>([]);
    const [isMobileOpen, setIsMobileOpen] = useState(false);
    const [isNewOpen, setIsNewOpen] = useState(false);
    const [deletingSessionId, setDeletingSessionId] = useState<string | null>(
        null,
    );

    useEffect(() => {
        loadSessions(true);
        fetchConfigs()
            .then(setConfigs)
            .catch(() => {});
        return () => {
            // ページ離脱時に store をクリア
            reset();
        };
    }, [loadSessions, reset]);

    const handleConfirmDelete = async () => {
        if (!deletingSessionId) return;
        setDeletingSessionId(null);
        await removeSession(deletingSessionId);
    };

    const handleCreate = async (configName: string) => {
        await createNewSession(configName);
        setIsMobileOpen(false);
    };

    return (
        // 高さの低い画面では min-h で一覧の高さを確保し、外側の main でスクロールさせる
        <div className="flex h-[calc(100svh-var(--mobile-bar-height)-var(--page-pad-top)-var(--page-pad-bottom))] min-h-112 w-full rounded-lg border lg:h-[calc(100svh-var(--page-pad-top)-var(--page-pad-bottom))]">
            <h1 className="sr-only">チャット</h1>
            <SessionSidebar
                sessions={sessions}
                activeSessionId={activeSessionId}
                hasMore={hasMore}
                isLoading={isLoadingList}
                onSelect={selectSession}
                onDelete={setDeletingSessionId}
                onLoadMore={loadMoreSessions}
                onNew={() => setIsNewOpen(true)}
                isOpen={isMobileOpen}
                onClose={() => setIsMobileOpen(false)}
            />

            <main className="bg-background flex min-w-0 flex-1 flex-col">
                <div className="flex items-center gap-2 border-b px-3 py-2 md:hidden">
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => setIsMobileOpen(true)}
                        aria-label="サイドバーを開く"
                    >
                        <Menu className="size-5" />
                    </Button>
                    <span className="text-ink-strong text-sm font-semibold">
                        チャット
                    </span>
                </div>
                <div className="min-h-0 flex-1">
                    <ChatThreadView />
                </div>
            </main>

            <NewSessionDialog
                configs={configs}
                open={isNewOpen}
                onClose={() => setIsNewOpen(false)}
                onCreate={handleCreate}
            />

            <ConfirmDialog
                open={deletingSessionId !== null}
                title="チャットを削除"
                confirmLabel="削除"
                destructive
                onConfirm={handleConfirmDelete}
                onCancel={() => setDeletingSessionId(null)}
            >
                このチャットを削除します。よろしいですか？
            </ConfirmDialog>
        </div>
    );
}
