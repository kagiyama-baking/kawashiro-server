import {
    type AppendMessage,
    type AssistantRuntime,
    MessageNotSentError,
    type ThreadMessageLike,
    useExternalStoreRuntime,
} from '@assistant-ui/react';
import { useMemo } from 'react';
import { useNavigate } from 'react-router';
import {
    selectIsSendDisabled,
    type SendResult,
    type TurnHooks,
    useChatStore,
} from '@/stores/chat-store';
import type { ChatAudioState, ChatUiMessage, ChatUiStatus } from '@/types/talk';

/** メッセージの部品が `metadata.custom` から読むサーバー側の値。 */
export interface ChatMessageCustom {
    readonly serverId: number | null;
    readonly sequence: number | null;
    readonly audio_url: string | null;
    readonly audio_format: string;
    readonly audio_size_bytes: number;
    readonly audioState: ChatAudioState;
    readonly audioError: string | null;
}

const ASSISTANT_STATUS: Record<
    ChatUiStatus,
    NonNullable<ThreadMessageLike['status']>
> = {
    streaming: { type: 'running' },
    complete: { type: 'complete', reason: 'stop' },
    cancelled: { type: 'incomplete', reason: 'cancelled' },
};

// 参照が変わると assistant-ui の変換キャッシュが捨てられるので、モジュールに置く
function convertMessage(message: ChatUiMessage): ThreadMessageLike {
    const custom: ChatMessageCustom & Record<string, unknown> = {
        serverId: message.id,
        sequence: message.sequence,
        audio_url: message.audio_url,
        audio_format: message.audio_format,
        audio_size_bytes: message.audio_size_bytes,
        audioState: message.audioState,
        audioError: message.audioError,
    };
    return {
        id: message.localId,
        role: message.role,
        content: [{ type: 'text', text: message.content }],
        createdAt: message.created_at
            ? new Date(message.created_at)
            : undefined,
        status:
            message.role === 'assistant'
                ? ASSISTANT_STATUS[message.uiStatus]
                : undefined,
        metadata: { custom },
    };
}

function textOf(message: AppendMessage): string {
    return message.content
        .flatMap((part) => (part.type === 'text' ? [part.text] : []))
        .join('');
}

/**
 * 送れなかったことを assistant-ui に伝え、入力文を入力欄へ、編集文を編集欄へ戻させる。
 * 編集を開き直すには元のメッセージが runtime に戻っている必要があり、それは描画後の
 * effect で届くので、1 度タスクを譲ってから投げる。
 */
async function throwIfNotSent(result: SendResult): Promise<void> {
    if (result === 'sent') return;
    await new Promise((resolve) => setTimeout(resolve, 0));
    throw new MessageNotSentError();
}

/**
 * Zustand のストアを assistant-ui の runtime へつなぐ。
 *
 * 履歴はサーバーが持つので `setMessages` は渡さず、分岐も持たない。渡さなければ、
 * 停止しても発話は残り入力欄も変わらない（assistant-ui の標準の動作）。
 */
export function useChatRuntime(): AssistantRuntime {
    const messages = useChatStore((s) => s.messages);
    const isRunning = useChatStore((s) => s.isRunning);
    const isLoading = useChatStore((s) => s.isLoadingDetail);
    const isSendDisabled = useChatStore(selectIsSendDisabled);
    const navigate = useNavigate();

    const callbacks = useMemo(() => {
        // 送信の途中で変わるセッションに URL を合わせる
        const hooks: TurnHooks = {
            onSessionCreated: (id) => {
                navigate(`/talk/${id}`, { replace: true });
            },
            onSessionAbandoned: () => {
                navigate('/talk', { replace: true });
            },
        };
        return {
            onNew: async (message: AppendMessage) => {
                const result = await useChatStore
                    .getState()
                    .sendMessage(textOf(message), hooks);
                await throwIfNotSent(result);
            },
            onEdit: async (message: AppendMessage) => {
                const result = await useChatStore
                    .getState()
                    .editMessage(
                        message.sourceId ?? '',
                        textOf(message),
                        hooks,
                    );
                await throwIfNotSent(result);
            },
            onReload: async (parentId: string | null) => {
                if (parentId === null) return;
                await useChatStore.getState().regenerate(parentId, hooks);
            },
            onCancel: async () => {
                useChatStore.getState().cancelRun();
            },
        };
    }, [navigate]);

    const adapter = useMemo(
        () => ({
            messages,
            convertMessage,
            isRunning,
            isLoading,
            isSendDisabled,
            ...callbacks,
        }),
        [messages, isRunning, isLoading, isSendDisabled, callbacks],
    );

    return useExternalStoreRuntime(adapter);
}
