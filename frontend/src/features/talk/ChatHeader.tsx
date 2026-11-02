import { useAuiState } from '@assistant-ui/react';
import { Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { Button } from '@/components/ui/button';
import { countPlayableAudios } from '@/lib/audio/bundleLoader';
import { useChatStore } from '@/stores/chat-store';
import type { ChatSessionMessage, ChatUiMessage } from '@/types/talk';
import { AudioBundleDownload } from './AudioBundleDownload';
import { AudioBundlePlay } from './AudioBundlePlay';
import { PresetPicker } from './PresetPicker';
import { SessionTitleEditor } from './SessionTitleEditor';

function isSaved(
    message: ChatUiMessage,
): message is ChatUiMessage & ChatSessionMessage {
    return (
        message.id !== null &&
        message.sequence !== null &&
        message.created_at !== null
    );
}

/** 音声の一括操作。音声が 1 件もなければ出さない。 */
function BulkAudioActions({ sessionId }: { readonly sessionId: string }) {
    const messages = useChatStore((s) => s.messages);
    const deleteAllAudio = useChatStore((s) => s.deleteAllAudio);
    const isBusy = useChatStore((s) => s.isRunning || s.isSyncing);
    const [isConfirming, setIsConfirming] = useState(false);
    const saved = useMemo(() => messages.filter(isSaved), [messages]);

    if (countPlayableAudios(saved) === 0) return null;

    const handleConfirm = async () => {
        setIsConfirming(false);
        await deleteAllAudio();
    };

    return (
        <div className="flex flex-wrap items-center gap-1.5">
            <AudioBundlePlay
                sessionId={sessionId}
                messages={saved}
                disabled={isBusy}
            />
            <AudioBundleDownload
                sessionId={sessionId}
                messages={saved}
                disabled={isBusy}
            />
            <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsConfirming(true)}
                disabled={isBusy}
            >
                <Trash2 />
                音声を全削除
            </Button>
            <ConfirmDialog
                open={isConfirming}
                title="音声を全削除"
                confirmLabel="全て削除"
                destructive
                onConfirm={handleConfirm}
                onCancel={() => setIsConfirming(false)}
            >
                このチャットの音声ファイルを全て削除します。よろしいですか？
            </ConfirmDialog>
        </div>
    );
}

/** タイトル、プリセット、音声の一括操作。会話が始まるまでは出さない。 */
export function ChatHeader() {
    const session = useChatStore((s) => s.activeSession);
    const updateActiveTitle = useChatStore((s) => s.updateActiveTitle);
    const isEmpty = useAuiState((s) => s.thread.isEmpty);

    if (!session || isEmpty) return null;

    return (
        <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 border-b px-4 py-2">
            <div className="flex min-w-0 flex-1 basis-56 items-center gap-3">
                <SessionTitleEditor
                    title={session.title}
                    onSave={updateActiveTitle}
                />
                <PresetPicker />
            </div>
            <BulkAudioActions sessionId={session.id} />
        </header>
    );
}
