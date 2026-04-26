import { Menu } from 'lucide-react';
import { useEffect, useState } from 'react';
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

    const handleDeleteSession = async (id: string) => {
        if (!confirm('このチャットを削除します。よろしいですか？')) return;
        await removeSession(id);
    };

    const handleCreate = async (configName: string) => {
        await createNewSession(configName);
        setIsMobileOpen(false);
    };

    return (
        <div className="flex h-[calc(100vh-4rem)] w-full">
            <SessionSidebar
                sessions={sessions}
                activeSessionId={activeSessionId}
                hasMore={hasMore}
                isLoading={isLoadingList}
                onSelect={selectSession}
                onDelete={handleDeleteSession}
                onLoadMore={loadMoreSessions}
                onNew={() => setIsNewOpen(true)}
                isOpen={isMobileOpen}
                onClose={() => setIsMobileOpen(false)}
            />

            <main className="bg-background flex min-w-0 flex-1 flex-col">
                <div className="flex items-center gap-2 border-b border-[oklch(0.95_0_0/0.06)] px-3 py-2 md:hidden">
                    <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => setIsMobileOpen(true)}
                        aria-label="サイドバーを開く"
                    >
                        <Menu className="h-5 w-5" />
                    </Button>
                    <span className="font-heading text-[14px] font-semibold">
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
        </div>
    );
}
