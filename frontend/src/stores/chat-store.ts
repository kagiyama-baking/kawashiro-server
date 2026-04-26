import { create } from 'zustand';
import {
    bulkDeleteAudio as apiBulkDeleteAudio,
    createSession as apiCreateSession,
    deleteAudio as apiDeleteAudio,
    deleteSession as apiDeleteSession,
    editMessage as apiEditMessage,
    fetchAudioBlob as apiFetchAudioBlob,
    getSession as apiGetSession,
    listSessions as apiListSessions,
    postMessage as apiPostMessage,
    updateSessionTitle as apiUpdateSessionTitle,
} from '@/lib/api/talk';
import type { ChatSessionDetail, ChatSessionListItem } from '@/types/talk';
import { SESSION_LIST_DEFAULT_LIMIT } from '@/types/talk';

interface ChatStoreState {
    readonly sessions: ChatSessionListItem[];
    readonly sessionsCount: number;
    readonly sessionsOffset: number;
    readonly sessionsLimit: number;
    readonly hasMoreSessions: boolean;
    readonly activeSession: ChatSessionDetail | null;
    readonly activeSessionId: string | null;
    readonly isLoadingList: boolean;
    readonly isLoadingDetail: boolean;
    readonly isSendingMessage: boolean;
    readonly error: string | null;
    // 音声 Blob と Object URL のキャッシュ（msgId 単位）。
    // 同一音声は 1 回だけ fetch し、UI 側はこの両方を参照する。
    readonly audioObjectUrls: Map<number, string>;
    readonly audioBlobs: Map<number, Blob>;
}

interface ChatStoreActions {
    readonly loadSessions: (refresh?: boolean) => Promise<void>;
    readonly loadMoreSessions: () => Promise<void>;
    readonly selectSession: (id: string) => Promise<void>;
    readonly deselectSession: () => void;
    readonly createNewSession: (configName: string) => Promise<string>;
    readonly updateActiveTitle: (title: string) => Promise<void>;
    readonly removeSession: (id: string) => Promise<void>;
    readonly sendMessage: (content: string) => Promise<void>;
    readonly editAndResend: (msgId: number, content: string) => Promise<void>;
    readonly cancelMessage: () => void;
    readonly deleteMessageAudio: (msgId: number) => Promise<void>;
    readonly deleteAllAudio: () => Promise<void>;
    readonly ensureAudioObjectUrl: (msgId: number) => Promise<string | null>;
    readonly clearError: () => void;
    readonly reset: () => void;
}

type ChatStore = ChatStoreState & ChatStoreActions;

const initialState: ChatStoreState = {
    sessions: [],
    sessionsCount: 0,
    sessionsOffset: 0,
    sessionsLimit: SESSION_LIST_DEFAULT_LIMIT,
    hasMoreSessions: false,
    activeSession: null,
    activeSessionId: null,
    isLoadingList: false,
    isLoadingDetail: false,
    isSendingMessage: false,
    error: null,
    audioObjectUrls: new Map(),
    audioBlobs: new Map(),
};

// 進行中の AbortController（モジュールスコープでのみ持ち、state は不変に保つ）
let currentAbortController: AbortController | null = null;

function revokeAllAudioUrls(map: Map<number, string>) {
    map.forEach((url) => URL.revokeObjectURL(url));
}

function aggregateFromDetail(detail: ChatSessionDetail): ChatSessionListItem {
    return {
        id: detail.id,
        title: detail.title,
        config_name: detail.config_name,
        message_count: detail.messages.length,
        total_audio_bytes: detail.messages.reduce(
            (s, m) => s + m.audio_size_bytes,
            0,
        ),
        created_at: detail.created_at,
        updated_at: detail.updated_at,
    };
}

export const useChatStore = create<ChatStore>((set, get) => ({
    ...initialState,

    loadSessions: async (refresh = true) => {
        set({ isLoadingList: true, error: null });
        try {
            const offset = refresh ? 0 : get().sessionsOffset;
            const res = await apiListSessions({
                limit: get().sessionsLimit,
                offset,
            });
            set({
                sessions: refresh
                    ? [...res.results]
                    : [...get().sessions, ...res.results],
                sessionsCount: res.count,
                sessionsOffset: offset + res.results.length,
                hasMoreSessions: res.next !== null,
            });
        } catch {
            set({ error: 'セッション一覧の取得に失敗しました' });
        } finally {
            set({ isLoadingList: false });
        }
    },

    loadMoreSessions: async () => {
        if (!get().hasMoreSessions || get().isLoadingList) return;
        await get().loadSessions(false);
    },

    selectSession: async (id: string) => {
        if (get().activeSessionId === id && get().activeSession) return;
        const previousUrls = get().audioObjectUrls;
        revokeAllAudioUrls(previousUrls);
        set({
            activeSessionId: id,
            activeSession: null,
            isLoadingDetail: true,
            error: null,
            audioObjectUrls: new Map(),
            audioBlobs: new Map(),
        });
        try {
            const detail = await apiGetSession(id);
            set({ activeSession: detail });
        } catch {
            set({ error: 'セッション詳細の取得に失敗しました' });
        } finally {
            set({ isLoadingDetail: false });
        }
    },

    deselectSession: () => {
        revokeAllAudioUrls(get().audioObjectUrls);
        set({
            activeSession: null,
            activeSessionId: null,
            audioObjectUrls: new Map(),
            audioBlobs: new Map(),
        });
    },

    createNewSession: async (configName: string) => {
        set({ error: null });
        const detail = await apiCreateSession(configName);
        // 一覧の先頭に追加、active にする
        set({
            sessions: [aggregateFromDetail(detail), ...get().sessions],
            sessionsCount: get().sessionsCount + 1,
            activeSession: detail,
            activeSessionId: detail.id,
            audioObjectUrls: new Map(),
            audioBlobs: new Map(),
        });
        return detail.id;
    },

    updateActiveTitle: async (title: string) => {
        const id = get().activeSessionId;
        if (!id) return;
        const detail = await apiUpdateSessionTitle(id, title);
        set((state) => ({
            activeSession: detail,
            sessions: state.sessions.map((s) =>
                s.id === id ? aggregateFromDetail(detail) : s,
            ),
        }));
    },

    removeSession: async (id: string) => {
        await apiDeleteSession(id);
        set((state) => {
            const isActive = state.activeSessionId === id;
            if (isActive) revokeAllAudioUrls(state.audioObjectUrls);
            return {
                sessions: state.sessions.filter((s) => s.id !== id),
                sessionsCount: Math.max(0, state.sessionsCount - 1),
                activeSession: isActive ? null : state.activeSession,
                activeSessionId: isActive ? null : state.activeSessionId,
                audioObjectUrls: isActive ? new Map() : state.audioObjectUrls,
                audioBlobs: isActive ? new Map() : state.audioBlobs,
            };
        });
    },

    sendMessage: async (content: string) => {
        const sessionId = get().activeSessionId;
        if (!sessionId || get().isSendingMessage) return;

        const controller = new AbortController();
        currentAbortController = controller;
        set({ isSendingMessage: true, error: null });
        try {
            const detail = await apiPostMessage(sessionId, content, {
                signal: controller.signal,
            });
            set((state) => ({
                activeSession: detail,
                sessions: state.sessions.map((s) =>
                    s.id === detail.id ? aggregateFromDetail(detail) : s,
                ),
            }));
        } catch (err) {
            const isAbort =
                controller.signal.aborted ||
                (err instanceof Error && err.name === 'AbortError');
            if (!isAbort) {
                set({ error: '応答の生成に失敗しました' });
            }
        } finally {
            if (currentAbortController === controller) {
                currentAbortController = null;
            }
            set({ isSendingMessage: false });
        }
    },

    editAndResend: async (msgId: number, content: string) => {
        const sessionId = get().activeSessionId;
        if (!sessionId || get().isSendingMessage) return;

        // 編集対象以降の Object URL / Blob キャッシュを解放
        const session = get().activeSession;
        if (session) {
            const target = session.messages.find((m) => m.id === msgId);
            if (target) {
                const targetSeq = target.sequence;
                const newUrls = new Map(get().audioObjectUrls);
                const newBlobs = new Map(get().audioBlobs);
                session.messages.forEach((m) => {
                    if (m.sequence >= targetSeq) {
                        const url = newUrls.get(m.id);
                        if (url) {
                            URL.revokeObjectURL(url);
                            newUrls.delete(m.id);
                        }
                        newBlobs.delete(m.id);
                    }
                });
                set({ audioObjectUrls: newUrls, audioBlobs: newBlobs });
            }
        }

        const controller = new AbortController();
        currentAbortController = controller;
        set({ isSendingMessage: true, error: null });
        try {
            const detail = await apiEditMessage(sessionId, msgId, content, {
                signal: controller.signal,
            });
            set((state) => ({
                activeSession: detail,
                sessions: state.sessions.map((s) =>
                    s.id === detail.id ? aggregateFromDetail(detail) : s,
                ),
            }));
        } catch (err) {
            const isAbort =
                controller.signal.aborted ||
                (err instanceof Error && err.name === 'AbortError');
            if (!isAbort) {
                set({ error: '応答の再生成に失敗しました' });
            }
        } finally {
            if (currentAbortController === controller) {
                currentAbortController = null;
            }
            set({ isSendingMessage: false });
        }
    },

    cancelMessage: () => {
        currentAbortController?.abort();
    },

    deleteMessageAudio: async (msgId: number) => {
        const sessionId = get().activeSessionId;
        if (!sessionId) return;
        await apiDeleteAudio(sessionId, msgId);
        const urls = get().audioObjectUrls;
        const url = urls.get(msgId);
        if (url) {
            URL.revokeObjectURL(url);
            const nextUrls = new Map(urls);
            nextUrls.delete(msgId);
            const nextBlobs = new Map(get().audioBlobs);
            nextBlobs.delete(msgId);
            set({ audioObjectUrls: nextUrls, audioBlobs: nextBlobs });
        }
        // active session を更新
        const detail = get().activeSession;
        if (detail) {
            const updated: ChatSessionDetail = {
                ...detail,
                messages: detail.messages.map((m) =>
                    m.id === msgId
                        ? {
                              ...m,
                              audio_url: null,
                              audio_format: '',
                              audio_size_bytes: 0,
                          }
                        : m,
                ),
            };
            set((state) => ({
                activeSession: updated,
                sessions: state.sessions.map((s) =>
                    s.id === detail.id ? aggregateFromDetail(updated) : s,
                ),
            }));
        }
    },

    deleteAllAudio: async () => {
        const sessionId = get().activeSessionId;
        if (!sessionId) return;
        await apiBulkDeleteAudio(sessionId);
        revokeAllAudioUrls(get().audioObjectUrls);
        set({ audioObjectUrls: new Map(), audioBlobs: new Map() });
        const detail = get().activeSession;
        if (detail) {
            const updated: ChatSessionDetail = {
                ...detail,
                messages: detail.messages.map((m) => ({
                    ...m,
                    audio_url: null,
                    audio_format: '',
                    audio_size_bytes: 0,
                })),
            };
            set((state) => ({
                activeSession: updated,
                sessions: state.sessions.map((s) =>
                    s.id === detail.id ? aggregateFromDetail(updated) : s,
                ),
            }));
        }
    },

    ensureAudioObjectUrl: async (msgId: number) => {
        const sessionId = get().activeSessionId;
        if (!sessionId) return null;
        const cached = get().audioObjectUrls.get(msgId);
        if (cached) return cached;
        const blob = await apiFetchAudioBlob(sessionId, msgId);
        const url = URL.createObjectURL(blob);
        const nextUrls = new Map(get().audioObjectUrls);
        nextUrls.set(msgId, url);
        const nextBlobs = new Map(get().audioBlobs);
        nextBlobs.set(msgId, blob);
        set({ audioObjectUrls: nextUrls, audioBlobs: nextBlobs });
        return url;
    },

    clearError: () => set({ error: null }),

    reset: () => {
        revokeAllAudioUrls(get().audioObjectUrls);
        currentAbortController?.abort();
        currentAbortController = null;
        set({
            ...initialState,
            audioObjectUrls: new Map(),
            audioBlobs: new Map(),
        });
    },
}));
