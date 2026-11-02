import type {
    ChatSessionDetail,
    ChatSessionListItem,
    ChatUiMessage,
    GenerateConfig,
} from '@/types/talk';
import { CHAT_HISTORY_MAX_COUNT } from '@/types/talk';
import { aggregateFromDetail, mergeServerMessages } from './chat-messages';

export interface ChatStoreState {
    readonly sessions: readonly ChatSessionListItem[];
    readonly sessionsCount: number;
    readonly sessionsOffset: number;
    readonly hasMoreSessions: boolean;
    readonly isLoadingList: boolean;
    readonly configs: readonly GenerateConfig[];
    readonly selectedConfigName: string | null;
    readonly configsFailed: boolean;
    readonly activeSessionId: string | null;
    readonly activeSession: ChatSessionListItem | null;
    readonly messages: readonly ChatUiMessage[];
    // ChatThread の key。セッションを切り替えたときだけ変え、遅延作成ではリマウントさせない
    readonly threadKey: number;
    readonly isLoadingDetail: boolean;
    readonly isRunning: boolean;
    readonly isSyncing: boolean;
    readonly error: string | null;
    // 音声 Blob と Object URL のキャッシュ（サーバーのメッセージ id 単位）
    readonly audioObjectUrls: ReadonlyMap<number, string>;
    readonly audioBlobs: ReadonlyMap<number, Blob>;
}

export type SetChatState = (
    partial:
        | Partial<ChatStoreState>
        | ((state: ChatStoreState) => Partial<ChatStoreState>),
) => void;

export type GetChatState = () => ChatStoreState;

export const selectIsAtMessageLimit = (state: ChatStoreState): boolean =>
    state.messages.length >= CHAT_HISTORY_MAX_COUNT;

/** 読み込みに失敗した。セッションは決まっているが、履歴もプリセットも分からない状態。 */
export const selectHasLoadFailed = (state: ChatStoreState): boolean =>
    state.activeSessionId !== null &&
    state.activeSession === null &&
    !state.isLoadingDetail;

export const selectIsSendDisabled = (state: ChatStoreState): boolean =>
    state.isLoadingDetail ||
    state.isSyncing ||
    selectIsAtMessageLimit(state) ||
    selectHasLoadFailed(state) ||
    (state.activeSessionId === null && state.selectedConfigName === null);

let threadKeyCounter = 0;

function nextThreadKey(): number {
    threadKeyCounter += 1;
    return threadKeyCounter;
}

/** 表示中のセッションのない状態。threadKey を変えるので ChatThread はリマウントする。 */
export function emptyThread(): Partial<ChatStoreState> {
    return {
        activeSessionId: null,
        activeSession: null,
        messages: [],
        threadKey: nextThreadKey(),
        isLoadingDetail: false,
        isRunning: false,
        isSyncing: false,
        error: null,
        audioObjectUrls: new Map(),
        audioBlobs: new Map(),
    };
}

export const initialChatState: ChatStoreState = {
    sessions: [],
    sessionsCount: 0,
    sessionsOffset: 0,
    hasMoreSessions: false,
    isLoadingList: false,
    configs: [],
    selectedConfigName: null,
    configsFailed: false,
    activeSessionId: null,
    activeSession: null,
    messages: [],
    threadKey: nextThreadKey(),
    isLoadingDetail: false,
    isRunning: false,
    isSyncing: false,
    error: null,
    audioObjectUrls: new Map(),
    audioBlobs: new Map(),
};

/** 指定の音声のキャッシュを解放した状態を返す。 */
export function withoutAudioIds(
    state: ChatStoreState,
    ids: readonly number[],
): Partial<ChatStoreState> {
    const urls = new Map(state.audioObjectUrls);
    const blobs = new Map(state.audioBlobs);
    ids.forEach((id) => {
        const url = urls.get(id);
        if (url) URL.revokeObjectURL(url);
        urls.delete(id);
        blobs.delete(id);
    });
    return { audioObjectUrls: urls, audioBlobs: blobs };
}

export interface ChatStateUpdaters {
    /** 表示中のセッションのときだけメッセージを更新する。 */
    readonly updateMessages: (
        sessionId: string,
        update: (
            messages: readonly ChatUiMessage[],
        ) => readonly ChatUiMessage[],
    ) => void;
    /** 一覧とヘッダのセッション情報を更新する。 */
    readonly patchSession: (
        sessionId: string,
        patch: Partial<ChatSessionListItem>,
    ) => void;
    readonly moveSessionToTop: (sessionId: string) => void;
    /** サーバーの詳細へ揃える。localId は保つ。 */
    readonly applyServerDetail: (detail: ChatSessionDetail) => void;
    readonly dropFromList: (sessionId: string) => void;
}

export function createChatStateUpdaters(set: SetChatState): ChatStateUpdaters {
    return {
        updateMessages: (sessionId, update) => {
            set((state) =>
                state.activeSessionId === sessionId
                    ? { messages: update(state.messages) }
                    : state,
            );
        },
        patchSession: (sessionId, patch) => {
            set((state) => ({
                sessions: state.sessions.map((s) =>
                    s.id === sessionId ? { ...s, ...patch } : s,
                ),
                activeSession:
                    state.activeSession?.id === sessionId
                        ? { ...state.activeSession, ...patch }
                        : state.activeSession,
            }));
        },
        moveSessionToTop: (sessionId) => {
            set((state) => {
                const target = state.sessions.find((s) => s.id === sessionId);
                return target
                    ? {
                          sessions: [
                              target,
                              ...state.sessions.filter((s) => s !== target),
                          ],
                      }
                    : state;
            });
        },
        applyServerDetail: (detail) => {
            const item = aggregateFromDetail(detail);
            set((state) => ({
                messages: mergeServerMessages(state.messages, detail.messages),
                activeSession: item,
                sessions: state.sessions.map((s) =>
                    s.id === item.id ? item : s,
                ),
            }));
        },
        dropFromList: (sessionId) => {
            set((state) => ({
                sessions: state.sessions.filter((s) => s.id !== sessionId),
                sessionsCount: Math.max(0, state.sessionsCount - 1),
                sessionsOffset: Math.max(0, state.sessionsOffset - 1),
            }));
        },
    };
}
