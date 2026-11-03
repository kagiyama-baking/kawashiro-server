import { AlertCircle, Loader2, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link, useNavigate } from 'react-router';
import { Button } from '@/components/ui/button';
import {
    selectHasLoadFailed,
    selectIsAtMessageLimit,
    useChatStore,
} from '@/stores/chat-store';
import { CHAT_HISTORY_MAX_COUNT } from '@/types/talk';

function ErrorNotice({
    message,
    action,
}: {
    readonly message: string;
    readonly action?: ReactNode;
}) {
    return (
        <div
            role="alert"
            className="bg-card border-l-destructive flex items-start gap-2.5 rounded-lg border border-l-3 py-2 pr-1.5 pl-3.5"
        >
            <AlertCircle className="text-destructive mt-[0.3rem] size-4 shrink-0" />
            <p className="text-destructive min-w-0 flex-1 text-sm wrap-anywhere">
                {message}
            </p>
            {action}
        </div>
    );
}

/** 読み込みに失敗したチャットを読み直す。消えていたら新規チャットへ移る。 */
function RetryButton() {
    const retryOpenSession = useChatStore((s) => s.retryOpenSession);
    const navigate = useNavigate();

    const handleClick = async () => {
        const result = await retryOpenSession();
        if (result === 'not-found') navigate('/talk', { replace: true });
    };

    return (
        <Button
            type="button"
            variant="outline"
            size="xs"
            className="shrink-0"
            onClick={() => void handleClick()}
        >
            再読み込み
        </Button>
    );
}

/** 入力欄の上に出す知らせ。失敗、件数の上限、停止後の同期。 */
export function ChatNotices() {
    const error = useChatStore((s) => s.error);
    const clearError = useChatStore((s) => s.clearError);
    const isSyncing = useChatStore((s) => s.isSyncing);
    const isRunning = useChatStore((s) => s.isRunning);
    const isAtLimit = useChatStore(selectIsAtMessageLimit);
    const hasLoadFailed = useChatStore(selectHasLoadFailed);
    const configsFailed = useChatStore(
        (s) => s.configsFailed && s.activeSessionId === null,
    );

    return (
        <div className="mb-2 flex flex-col gap-2 empty:hidden">
            {configsFailed && (
                <ErrorNotice message="プリセットを取得できませんでした。ページを再読み込みしてください。" />
            )}
            {hasLoadFailed && (
                <ErrorNotice
                    message={error ?? 'チャットの読み込みに失敗しました'}
                    action={<RetryButton />}
                />
            )}
            {error && !hasLoadFailed && (
                <ErrorNotice
                    message={error}
                    action={
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon-xs"
                            onClick={clearError}
                            aria-label="メッセージを閉じる"
                        >
                            <X />
                        </Button>
                    }
                />
            )}
            {isAtLimit && !isRunning && (
                <div
                    role="status"
                    className="bg-card border-l-primary flex flex-wrap items-center justify-between gap-x-3 gap-y-1 rounded-lg border border-l-3 px-3.5 py-2 text-sm"
                >
                    <p>
                        このチャットは上限（{CHAT_HISTORY_MAX_COUNT}{' '}
                        件）に達しました。続けるには新しいチャットを始めてください。
                    </p>
                    <Link
                        to="/talk"
                        className="text-primary hover:text-primary-hover shrink-0 font-medium underline underline-offset-2 transition-colors"
                    >
                        新しいチャット
                    </Link>
                </div>
            )}
            {isSyncing && (
                <p
                    role="status"
                    className="text-ink-subtle flex items-center gap-2 text-xs"
                >
                    <Loader2 className="size-3 animate-spin" />
                    保存された内容を確認しています…
                </p>
            )}
        </div>
    );
}
