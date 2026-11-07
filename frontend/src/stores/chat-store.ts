import { HTTPError } from 'ky';
import { create } from 'zustand';
import {
    bulkDeleteAudio as apiBulkDeleteAudio,
    deleteAudio as apiDeleteAudio,
    deleteSession as apiDeleteSession,
    fetchAudioBlob as apiFetchAudioBlob,
    fetchSettings as apiFetchSettings,
    getSession as apiGetSession,
    listSessions as apiListSessions,
    updateSessionTitle as apiUpdateSessionTitle,
} from '@/lib/api/talk';
import { SESSION_LIST_DEFAULT_LIMIT } from '@/types/talk';
import {
    aggregateFromDetail,
    clearAudio,
    fromServerMessage,
} from './chat-messages';
import {
    type ChatStoreState,
    createChatStateUpdaters,
    emptyThread,
    initialChatState,
    selectHasLoadFailed,
    withoutAudioIds,
} from './chat-state';
import { type ChatTurns, createChatTurns } from './chat-turn';

export {
    selectHasLoadFailed,
    selectIsAtMessageLimit,
    selectIsSendDisabled,
} from './chat-state';
export type { SendResult, TurnHooks } from './chat-turn';

export type OpenSessionResult = 'ok' | 'not-found' | 'error' | 'stale';

/** セッションの削除の結果。active なら表示中のセッションを消したので新規チャットへ移る。 */
export type RemoveSessionResult = 'active' | 'other' | 'failed';

interface ChatStoreActions extends ChatTurns {
    readonly loadSessions: (refresh?: boolean) => Promise<void>;
    readonly loadMoreSessions: () => Promise<void>;
    readonly loadSettings: () => Promise<void>;
    /** Talk 設定を選ぶ。覚えておき、シーンは「なし」に戻す。 */
    readonly selectSetting: (id: number) => void;
    /** シーンを選ぶ。null は「なし」。シーンは覚えない。 */
    readonly selectSkill: (name: string | null) => void;
    readonly openSession: (id: string) => Promise<OpenSessionResult>;
    readonly retryOpenSession: () => Promise<OpenSessionResult>;
    readonly startNewChat: () => void;
    readonly updateActiveTitle: (title: string) => Promise<void>;
    readonly removeSession: (id: string) => Promise<RemoveSessionResult>;
    readonly deleteMessageAudio: (messageId: number) => Promise<void>;
    readonly deleteAllAudio: () => Promise<void>;
    readonly ensureAudioObjectUrl: (
        messageId: number,
    ) => Promise<string | null>;
    readonly clearError: () => void;
    readonly reset: () => void;
}

type ChatStore = ChatStoreState & ChatStoreActions;

const SELECTED_SETTING_KEY = 'talk-selected-setting';
const AUDIO_DELETE_FAILED = '音声を削除できませんでした';
const SESSION_NOT_FOUND = 'チャットが見つかりませんでした';
// id は URL から来て API のパスに入る。react-router は %2F を / に戻すので、
// 細工したリンクで別の API を呼ばれないよう、UUID に使う文字だけを通す。
const SESSION_ID_PATTERN = /^[0-9a-zA-Z-]+$/;

const pendingAudio = new Map<number, Promise<string | null>>();
let openToken = 0;
let listToken = 0;
let settingsToken = 0;

function readSelectedSetting(): string | null {
    try {
        return localStorage.getItem(SELECTED_SETTING_KEY);
    } catch {
        return null;
    }
}

function writeSelectedSetting(id: number): void {
    try {
        localStorage.setItem(SELECTED_SETTING_KEY, String(id));
    } catch {
        // 保存できなくても今回の選択は使える
    }
}

export const useChatStore = create<ChatStore>((set, get) => {
    const updaters = createChatStateUpdaters(set);
    const { updateMessages, patchSession, dropFromList } = updaters;
    const turns = createChatTurns(set, get, updaters);

    /** 表示中のセッションを離れる。遅れて届く読み込みの結果も捨てる。 */
    const leaveThread = () => {
        turns.leaveForAnotherThread();
        openToken += 1;
        get().audioObjectUrls.forEach((url) => URL.revokeObjectURL(url));
        // 取得中の音声は結果を捨てるので、戻ってきたら取り直す
        pendingAudio.clear();
    };

    const loadSession = async (id: string): Promise<OpenSessionResult> => {
        const token = openToken;
        try {
            const detail = await apiGetSession(id);
            if (token !== openToken) return 'stale';
            const item = aggregateFromDetail(detail);
            set((state) => ({
                activeSession: item,
                messages: detail.messages.map(fromServerMessage),
                isLoadingDetail: false,
                sessions: state.sessions.map((s) => (s.id === id ? item : s)),
            }));
            return 'ok';
        } catch (error) {
            if (token !== openToken) return 'stale';
            if (error instanceof HTTPError && error.response.status === 404) {
                set({ ...emptyThread(), error: SESSION_NOT_FOUND });
                return 'not-found';
            }
            set({
                isLoadingDetail: false,
                error: 'チャットの読み込みに失敗しました',
            });
            return 'error';
        }
    };

    return {
        ...initialChatState,
        ...turns.actions,

        loadSessions: async (refresh = true) => {
            listToken += 1;
            const token = listToken;
            set({ isLoadingList: true });
            try {
                const offset = refresh ? 0 : get().sessionsOffset;
                const res = await apiListSessions({
                    limit: SESSION_LIST_DEFAULT_LIMIT,
                    offset,
                });
                if (token !== listToken) return;
                set((state) => {
                    const known = new Set(state.sessions.map((s) => s.id));
                    return {
                        sessions: refresh
                            ? [...res.results]
                            : [
                                  ...state.sessions,
                                  ...res.results.filter(
                                      (s) => !known.has(s.id),
                                  ),
                              ],
                        sessionsCount: res.count,
                        sessionsOffset: offset + res.results.length,
                        hasMoreSessions: res.next !== null,
                        isLoadingList: false,
                    };
                });
            } catch {
                if (token !== listToken) return;
                set({
                    error: 'セッション一覧の取得に失敗しました',
                    isLoadingList: false,
                });
            }
        },

        loadMoreSessions: async () => {
            if (!get().hasMoreSessions || get().isLoadingList) return;
            await get().loadSessions(false);
        },

        loadSettings: async () => {
            settingsToken += 1;
            const token = settingsToken;
            try {
                const settings = await apiFetchSettings();
                if (token !== settingsToken) return;
                const remembered = readSelectedSetting();
                const selected =
                    settings.find((s) => String(s.id) === remembered) ??
                    settings[0];
                set({
                    settings,
                    selectedSettingId: selected?.id ?? null,
                    selectedSkillName: null,
                    settingsFailed: false,
                });
            } catch {
                if (token !== settingsToken) return;
                set({ settingsFailed: true });
            }
        },

        selectSetting: (id) => {
            writeSelectedSetting(id);
            set({ selectedSettingId: id, selectedSkillName: null });
        },

        selectSkill: (name) => set({ selectedSkillName: name }),

        openSession: async (id) => {
            if (get().activeSessionId === id) return 'ok';
            leaveThread();
            if (!SESSION_ID_PATTERN.test(id)) {
                set({ ...emptyThread(), error: SESSION_NOT_FOUND });
                return 'not-found';
            }
            set({
                ...emptyThread(),
                activeSessionId: id,
                isLoadingDetail: true,
            });
            return loadSession(id);
        },

        retryOpenSession: async () => {
            const id = get().activeSessionId;
            if (id === null || !selectHasLoadFailed(get())) return 'stale';
            set({ isLoadingDetail: true, error: null });
            return loadSession(id);
        },

        startNewChat: () => {
            if (get().activeSessionId === null) return;
            leaveThread();
            set(emptyThread());
        },

        updateActiveTitle: async (title) => {
            const id = get().activeSessionId;
            if (!id) return;
            try {
                const detail = await apiUpdateSessionTitle(id, title);
                patchSession(id, { title: detail.title });
            } catch {
                set({ error: 'タイトルを変更できませんでした' });
            }
        },

        removeSession: async (id) => {
            try {
                await apiDeleteSession(id);
            } catch {
                set({ error: 'チャットを削除できませんでした' });
                return 'failed';
            }
            const isActive = get().activeSessionId === id;
            turns.closeSessionRuns(id);
            if (isActive) {
                leaveThread();
                set(emptyThread());
            }
            dropFromList(id);
            return isActive ? 'active' : 'other';
        },

        deleteMessageAudio: async (messageId) => {
            const sessionId = get().activeSessionId;
            if (!sessionId) return;
            try {
                await apiDeleteAudio(sessionId, messageId);
            } catch {
                set({ error: AUDIO_DELETE_FAILED });
                return;
            }
            if (get().activeSessionId !== sessionId) return;
            set((state) => withoutAudioIds(state, [messageId]));
            updateMessages(sessionId, (messages) =>
                clearAudio(messages, (m) => m.id === messageId),
            );
            patchSession(sessionId, {
                total_audio_bytes: get().messages.reduce(
                    (sum, m) => sum + m.audio_size_bytes,
                    0,
                ),
            });
        },

        deleteAllAudio: async () => {
            const sessionId = get().activeSessionId;
            if (!sessionId) return;
            try {
                await apiBulkDeleteAudio(sessionId);
            } catch {
                set({ error: AUDIO_DELETE_FAILED });
                return;
            }
            patchSession(sessionId, { total_audio_bytes: 0 });
            if (get().activeSessionId !== sessionId) return;
            set((state) =>
                withoutAudioIds(state, [...state.audioObjectUrls.keys()]),
            );
            updateMessages(sessionId, (messages) =>
                clearAudio(messages, () => true),
            );
        },

        ensureAudioObjectUrl: (messageId) => {
            const { activeSessionId, audioObjectUrls, threadKey } = get();
            if (!activeSessionId) return Promise.resolve(null);
            const cached = audioObjectUrls.get(messageId);
            if (cached) return Promise.resolve(cached);
            const pending = pendingAudio.get(messageId);
            if (pending) return pending;

            const task = apiFetchAudioBlob(activeSessionId, messageId)
                .then((blob) => {
                    if (get().threadKey !== threadKey) return null;
                    const url = URL.createObjectURL(blob);
                    set((state) => ({
                        audioObjectUrls: new Map(state.audioObjectUrls).set(
                            messageId,
                            url,
                        ),
                        audioBlobs: new Map(state.audioBlobs).set(
                            messageId,
                            blob,
                        ),
                    }));
                    return url;
                })
                .finally(() => {
                    if (pendingAudio.get(messageId) === task) {
                        pendingAudio.delete(messageId);
                    }
                });
            pendingAudio.set(messageId, task);
            return task;
        },

        clearError: () => set({ error: null }),

        reset: () => {
            turns.closeAllRuns();
            leaveThread();
            listToken += 1;
            settingsToken += 1;
            set({ ...initialChatState, ...emptyThread() });
        },
    };
});
