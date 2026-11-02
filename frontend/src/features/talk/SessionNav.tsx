import { Loader2, Plus } from 'lucide-react';
import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { GHOST_ON_SIDEBAR } from '@/components/layout/sidebar-styles';
import { Button } from '@/components/ui/button';
import { useChatStore } from '@/stores/chat-store';
import type { ChatSessionListItem } from '@/types/talk';
import { SessionListItem } from './SessionListItem';

interface SessionNavProps {
    readonly onNavigate?: () => void;
}

/** サイドバーのチャット一覧。初期チャンクに載るので assistant-ui に依存させない。 */
export function SessionNav({ onNavigate }: SessionNavProps) {
    const sessions = useChatStore((s) => s.sessions);
    const hasMore = useChatStore((s) => s.hasMoreSessions);
    const isLoading = useChatStore((s) => s.isLoadingList);
    const loadMoreSessions = useChatStore((s) => s.loadMoreSessions);
    const removeSession = useChatStore((s) => s.removeSession);
    const navigate = useNavigate();
    const [deleting, setDeleting] = useState<ChatSessionListItem | null>(null);

    const handleConfirmDelete = async () => {
        if (!deleting) return;
        const { id } = deleting;
        setDeleting(null);
        const result = await removeSession(id);
        // 表示中のチャットを消したときだけ移る。応答を待つ間に別のチャットへ移っていたら移らない
        if (result === 'active') navigate('/talk', { replace: true });
    };

    return (
        <div className="flex min-h-56 flex-1 flex-col gap-2.5 px-[0.7rem]">
            <NavLink
                to="/talk"
                end
                onClick={onNavigate}
                className="border-sidebar-border text-sidebar-foreground hover:bg-sidebar-hover hover:text-sidebar-accent-foreground aria-[current=page]:bg-sidebar-accent aria-[current=page]:text-sidebar-accent-foreground flex h-9 shrink-0 items-center gap-2 rounded-md border px-3 text-[0.8rem] tracking-[0.06em] transition-colors"
            >
                <Plus className="size-4" />
                新しいチャット
            </NavLink>

            <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
                {sessions.length === 0 && !isLoading && (
                    <p className="text-sidebar-muted-foreground px-3 py-2 text-xs">
                        まだ履歴がありません
                    </p>
                )}
                <ul className="flex flex-col gap-0.5 empty:hidden">
                    {sessions.map((item) => (
                        <SessionListItem
                            key={item.id}
                            item={item}
                            onDelete={setDeleting}
                            onNavigate={onNavigate}
                        />
                    ))}
                </ul>
                {hasMore && (
                    <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => void loadMoreSessions()}
                        disabled={isLoading}
                        className={`${GHOST_ON_SIDEBAR} mt-1 w-full shrink-0`}
                    >
                        {isLoading ? (
                            <Loader2 className="animate-spin" />
                        ) : (
                            'もっと読み込む'
                        )}
                    </Button>
                )}
            </div>

            <ConfirmDialog
                open={deleting !== null}
                title="チャットを削除"
                confirmLabel="削除"
                destructive
                onConfirm={handleConfirmDelete}
                onCancel={() => setDeleting(null)}
            >
                「{deleting?.title || '（無題）'}
                」を削除します。メッセージと音声も消えます。よろしいですか？
            </ConfirmDialog>
        </div>
    );
}
