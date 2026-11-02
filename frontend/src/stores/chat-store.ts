import { HTTPError } from 'ky';
import { create } from 'zustand';
import { extractApiErrorMessage } from '@/lib/api/errors';
import {
    bulkDeleteAudio as apiBulkDeleteAudio,
    createSession as apiCreateSession,
    deleteAudio as apiDeleteAudio,
    deleteSession as apiDeleteSession,
    fetchAudioBlob as apiFetchAudioBlob,
    fetchConfigs as apiFetchConfigs,
    getSession as apiGetSession,
    listSessions as apiListSessions,
    streamEdit as apiStreamEdit,
    streamMessage as apiStreamMessage,
    updateSessionTitle as apiUpdateSessionTitle,
} from '@/lib/api/talk';
import type {
    ChatSessionDetail,
    ChatSessionListItem,
    ChatStreamEvent,
    ChatUiMessage,
    GenerateConfig,
} from '@/types/talk';
import {
    CHAT_HISTORY_MAX_COUNT,
    SESSION_LIST_DEFAULT_LIMIT,
} from '@/types/talk';
import {
    aggregateFromDetail,
    appendDelta,
    applyAudio,
    applyAudioError,
    applySaved,
    clearAudio,
    createLocalId,
    createUserMessage,
    finishPendingAudio,
    fromServerMessage,
    hasSameRows,
    markCancelled,
    mergeServerMessages,
    replaceFromTarget,
    rollbackMessages,
} from './chat-messages';

/** 送信の結果。not-sent なら入力文を入力欄へ戻す（呼び出し側が MessageNotSentError にする）。 */
export type SendResult = 'sent' | 'not-sent';
export type OpenSessionResult = 'ok' | 'not-found' | 'error' | 'stale';

/** 遅延作成したセッションの URL を呼び出し側で合わせるための通知。 */
export interface TurnHooks {
    readonly onSessionCreated?: (sessionId: string) => void;
    readonly onSessionAbandoned?: () => void;
}

interface ChatStoreState {
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

interface ChatStoreActions {
    readonly loadSessions: (refresh?: boolean) => Promise<void>;
    readonly loadMoreSessions: () => Promise<void>;
    readonly loadConfigs: () => Promise<void>;
    readonly selectConfig: (name: string) => void;
    readonly openSession: (id: string) => Promise<OpenSessionResult>;
    readonly startNewChat: () => void;
    readonly updateActiveTitle: (title: string) => Promise<void>;
    readonly removeSession: (id: string) => Promise<void>;
    readonly sendMessage: (
        content: string,
        hooks?: TurnHooks,
    ) => Promise<SendResult>;
    readonly editMessage: (
        localId: string,
        content: string,
    ) => Promise<SendResult>;
    readonly regenerate: (userLocalId: string) => Promise<void>;
    readonly cancelRun: () => void;
    readonly deleteMessageAudio: (messageId: number) => Promise<void>;
    readonly deleteAllAudio: () => Promise<void>;
    readonly ensureAudioObjectUrl: (
        messageId: number,
    ) => Promise<string | null>;
    readonly clearError: () => void;
    readonly reset: () => void;
}

type ChatStore = ChatStoreState & ChatStoreActions;

export const selectIsAtMessageLimit = (state: ChatStoreState): boolean =>
    state.messages.length >= CHAT_HISTORY_MAX_COUNT;

export const selectIsSendDisabled = (state: ChatStoreState): boolean =>
    state.isLoadingDetail ||
    state.isSyncing ||
    selectIsAtMessageLimit(state) ||
    (state.activeSessionId === null && state.selectedConfigName === null);

const SYNC_INTERVAL_MS = 500;
const SYNC_TIMEOUT_MS = 10_000;
const SELECTED_CONFIG_KEY = 'talk-selected-config';

const SEND_FAILED = '応答の生成に失敗しました';
const CREATE_FAILED = 'チャットを作成できませんでした';
const NOT_SAVED =
    '応答が途中で止まり、この発言は保存されませんでした。入力欄へ戻しています。';
const SYNC_DIFFERS =
    'サーバーの内容と食い違っていたので、サーバーの内容に揃えました。';
const SYNC_FAILED =
    'サーバーの状態を確認できませんでした。ページを再読み込みしてください。';
const UNSAVED_MESSAGE =
    '保存が確認できていないメッセージは編集できません。ページを再読み込みしてください。';

// 中断の理由。fetch は signal.reason でリジェクトするので AbortError の形にしておく
const STOP = new DOMException('ユーザーが停止した', 'AbortError');
const LEAVE = new DOMException('チャットを離れた', 'AbortError');

/** 本文を生成している run。保存が済むとここから外れて backgroundRuns へ移る。 */
interface CurrentRun {
    readonly controller: AbortController;
    readonly restore: readonly ChatUiMessage[];
    // セッションの作成を待っている間は false。まだ何も送っていないので同期が要らない
    readonly posted: boolean;
}

/** 1 回の送信または編集の文脈。 */
interface TurnContext {
    readonly controller: AbortController;
    readonly sessionId: string;
    readonly threadKey: number;
    readonly restore: readonly ChatUiMessage[];
    readonly userLocalId: string;
    readonly assistantLocalId: string;
    readonly createdSession: boolean;
    readonly hooks: TurnHooks;
    // 同期の判定。送信なら行が増えたこと、編集なら対象の行の id が変わったこと
    readonly isSaved: (detail: ChatSessionDetail) => boolean;
}

type SyncResult =
    | { readonly status: 'saved'; readonly detail: ChatSessionDetail }
    | { readonly status: 'gone' }
    | { readonly status: 'timeout'; readonly detail: ChatSessionDetail | null };

let currentRun: CurrentRun | null = null;
// 保存が済み、音声とタイトルを待っている run（controller → セッション id）
const backgroundRuns = new Map<AbortController, string>();
const pendingAudio = new Map<number, Promise<string | null>>();
let openToken = 0;
let listToken = 0;
let configsToken = 0;
let threadKeyCounter = 0;

function nextThreadKey(): number {
    threadKeyCounter += 1;
    return threadKeyCounter;
}

function delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function isNotFound(error: unknown): boolean {
    return error instanceof HTTPError && error.response.status === 404;
}

function readSelectedConfig(): string | null {
    try {
        return localStorage.getItem(SELECTED_CONFIG_KEY);
    } catch {
        return null;
    }
}

function writeSelectedConfig(name: string): void {
    try {
        localStorage.setItem(SELECTED_CONFIG_KEY, name);
    } catch {
        // 保存できなくても今回の選択は使える
    }
}

function discardSession(sessionId: string): void {
    apiDeleteSession(sessionId).catch(() => {});
}

const initialState: ChatStoreState = {
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

function emptyThread(): Partial<ChatStoreState> {
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

function withoutAudioIds(
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

function totalAudioBytes(messages: readonly ChatUiMessage[]): number {
    return messages.reduce((sum, m) => sum + m.audio_size_bytes, 0);
}

export const useChatStore = create<ChatStore>((set, get) => {
    /** セッションを離れる。音声とタイトルを待つ run は別のセッションを壊さないので止めない。 */
    const leaveThread = () => {
        currentRun?.controller.abort(LEAVE);
        currentRun = null;
        openToken += 1;
        get().audioObjectUrls.forEach((url) => URL.revokeObjectURL(url));
    };

    const updateMessages = (
        sessionId: string,
        update: (
            messages: readonly ChatUiMessage[],
        ) => readonly ChatUiMessage[],
    ) => {
        set((state) =>
            state.activeSessionId === sessionId
                ? { messages: update(state.messages) }
                : state,
        );
    };

    /** 一覧とヘッダのセッション情報を更新する。 */
    const patchSession = (
        sessionId: string,
        patch: Partial<ChatSessionListItem>,
    ) => {
        set((state) => ({
            sessions: state.sessions.map((s) =>
                s.id === sessionId ? { ...s, ...patch } : s,
            ),
            activeSession:
                state.activeSession?.id === sessionId
                    ? { ...state.activeSession, ...patch }
                    : state.activeSession,
        }));
    };

    const moveSessionToTop = (sessionId: string) => {
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
    };

    const applyServerDetail = (detail: ChatSessionDetail) => {
        const item = aggregateFromDetail(detail);
        set((state) => ({
            messages: mergeServerMessages(state.messages, detail.messages),
            activeSession: item,
            sessions: state.sessions.map((s) => (s.id === item.id ? item : s)),
        }));
    };

    const dropFromList = (sessionId: string) => {
        set((state) => ({
            sessions: state.sessions.filter((s) => s.id !== sessionId),
            sessionsCount: Math.max(0, state.sessionsCount - 1),
            sessionsOffset: Math.max(0, state.sessionsOffset - 1),
        }));
    };

    /** 表示中のセッションを手放して新規チャットの状態へ戻す。入力欄を保つためリマウントはさせない。 */
    const abandonSession = (ctx: TurnContext) => {
        dropFromList(ctx.sessionId);
        set({ activeSessionId: null, activeSession: null, messages: [] });
        ctx.hooks.onSessionAbandoned?.();
    };

    const isSameThread = (ctx: TurnContext) =>
        get().threadKey === ctx.threadKey;

    const detachRun = (controller: AbortController) => {
        if (currentRun?.controller === controller) currentRun = null;
    };

    /** 送信の失敗。楽観表示を戻し、遅延作成したばかりの空セッションは消す。 */
    const failTurn = (ctx: TurnContext, message: string): SendResult => {
        if (!isSameThread(ctx)) return 'not-sent';
        set((state) => ({
            messages: rollbackMessages(
                ctx.restore,
                state.messages,
                ctx.userLocalId,
            ),
            isRunning: false,
            isSyncing: false,
            error: message,
        }));
        if (ctx.createdSession) {
            discardSession(ctx.sessionId);
            abandonSession(ctx);
        }
        return 'not-sent';
    };

    const applyStreamEvent = (ctx: TurnContext, event: ChatStreamEvent) => {
        switch (event.type) {
            case 'delta':
                updateMessages(ctx.sessionId, (messages) =>
                    appendDelta(messages, ctx.assistantLocalId, event.text),
                );
                break;
            case 'audio':
                updateMessages(ctx.sessionId, (messages) =>
                    applyAudio(messages, event),
                );
                break;
            case 'audio_error':
                updateMessages(ctx.sessionId, (messages) =>
                    applyAudioError(messages, event.message_id, event.error),
                );
                break;
            case 'title':
                patchSession(ctx.sessionId, { title: event.title });
                break;
            case 'done':
                patchSession(ctx.sessionId, {
                    title: event.title,
                    message_count: event.message_count,
                    total_audio_bytes: event.total_audio_bytes,
                    updated_at: event.updated_at,
                });
                moveSessionToTop(ctx.sessionId);
                updateMessages(ctx.sessionId, (messages) =>
                    finishPendingAudio(messages, ctx.assistantLocalId),
                );
                break;
            default:
                break;
        }
    };

    /** 保存が済んだ。本文の生成は終わりなので、音声の合成中も次を打てるようにする。 */
    const applySavedTurn = (
        ctx: TurnContext,
        event: Extract<ChatStreamEvent, { type: 'message' }>,
    ) => {
        detachRun(ctx.controller);
        backgroundRuns.set(ctx.controller, ctx.sessionId);
        if (!isSameThread(ctx)) return;
        const state = get();
        const audioPending = state.configs.some(
            (c) => c.name === state.activeSession?.config_name && c.tts_enabled,
        );
        const messages = applySaved(state.messages, {
            userLocalId: ctx.userLocalId,
            assistantLocalId: ctx.assistantLocalId,
            user: event.user,
            assistant: event.assistant,
            audioPending,
        });
        // 編集で置き換わった行の音声は、もう戻らないので解放する
        const kept = new Set(messages.map((m) => m.id));
        const removedIds = ctx.restore.flatMap((m) =>
            m.id !== null && !kept.has(m.id) ? [m.id] : [],
        );
        set({
            ...withoutAudioIds(state, removedIds),
            messages,
            isRunning: false,
        });
    };

    /** 保存を確認するまで詳細を読み直す。 */
    const pollForSavedTurn = async (ctx: TurnContext): Promise<SyncResult> => {
        const deadline = Date.now() + SYNC_TIMEOUT_MS;
        let latest: ChatSessionDetail | null = null;
        for (;;) {
            try {
                latest = await apiGetSession(ctx.sessionId);
                if (ctx.isSaved(latest)) {
                    return { status: 'saved', detail: latest };
                }
            } catch (error) {
                if (isNotFound(error)) return { status: 'gone' };
            }
            if (Date.now() + SYNC_INTERVAL_MS > deadline) {
                return { status: 'timeout', detail: latest };
            }
            await delay(SYNC_INTERVAL_MS);
            if (!isSameThread(ctx)) {
                return { status: 'timeout', detail: latest };
            }
        }
    };

    /** 同期を諦めたときの後始末。結局どこまで保存されたかをサーバーの値で確定する。 */
    const settleTimedOutSync = (
        ctx: TurnContext,
        detail: ChatSessionDetail | null,
    ): SendResult => {
        if (detail === null) {
            set({ isSyncing: false, error: SYNC_FAILED });
            return 'sent';
        }
        if (!hasSameRows(ctx.restore, detail.messages)) {
            applyServerDetail(detail);
            set({ isSyncing: false, error: SYNC_DIFFERS });
            return 'sent';
        }
        return failTurn(ctx, NOT_SAVED);
    };

    /** 停止または接続切れのあと、サーバーが保存した内容へ揃える。 */
    const syncInterruptedTurn = async (
        ctx: TurnContext,
    ): Promise<SendResult> => {
        detachRun(ctx.controller);
        if (!isSameThread(ctx)) return 'sent';
        set((state) => ({
            isRunning: false,
            isSyncing: true,
            messages: markCancelled(state.messages),
        }));
        const result = await pollForSavedTurn(ctx);
        if (!isSameThread(ctx)) return 'sent';

        switch (result.status) {
            case 'saved':
                applyServerDetail(result.detail);
                set({ isSyncing: false });
                return 'sent';
            case 'gone':
                set({ isSyncing: false });
                abandonSession(ctx);
                return 'not-sent';
            default:
                return settleTimedOutSync(ctx, result.detail);
        }
    };

    /** 保存のあと done の前に切れた。音声の通知は来ないので、保存された値を読み直す。 */
    const refreshAfterLostStream = async (ctx: TurnContext) => {
        updateMessages(ctx.sessionId, (messages) =>
            finishPendingAudio(messages, ctx.assistantLocalId),
        );
        try {
            const detail = await apiGetSession(ctx.sessionId);
            const state = get();
            // 次のターンの表示を巻き戻さない
            if (
                state.activeSessionId === ctx.sessionId &&
                !state.isRunning &&
                !state.isSyncing
            ) {
                applyServerDetail(detail);
            }
        } catch {
            // 次の読み込みで揃う
        }
    };

    const consumeTurn = async (
        ctx: TurnContext,
        stream: AsyncIterable<ChatStreamEvent>,
    ): Promise<SendResult> => {
        const { controller } = ctx;
        let receivedAny = false;
        let saved = false;
        let finished = false;
        try {
            for await (const event of stream) {
                receivedAny = true;
                if (controller.signal.aborted) break;
                if (event.type === 'error') {
                    detachRun(controller);
                    return failTurn(ctx, event.error);
                }
                if (event.type === 'message') {
                    saved = true;
                    applySavedTurn(ctx, event);
                } else {
                    applyStreamEvent(ctx, event);
                }
                if (event.type === 'done') finished = true;
            }
        } catch (error) {
            // 応答が始まる前の失敗だけが「送れなかった」。読み取りの途中で切れた場合は
            // サーバーが途中までを保存するので、接続切れと同じく同期で確かめる。
            if (!controller.signal.aborted && !receivedAny) {
                detachRun(controller);
                const message = await extractApiErrorMessage(
                    error,
                    SEND_FAILED,
                );
                return failTurn(ctx, message);
            }
        } finally {
            backgroundRuns.delete(controller);
        }

        if (controller.signal.reason === LEAVE) return 'sent';
        if (!saved) return syncInterruptedTurn(ctx);
        if (!finished) await refreshAfterLostStream(ctx);
        return 'sent';
    };

    /** 新規チャットの最初の送信で使うセッションを作る。使えなければ null を返す。 */
    const createSessionForRun = async (
        controller: AbortController,
        configName: string,
        restore: readonly ChatUiMessage[],
        hooks: TurnHooks,
    ): Promise<string | null> => {
        let detail: ChatSessionDetail;
        try {
            detail = await apiCreateSession(configName);
        } catch (error) {
            if (currentRun?.controller !== controller) return null;
            const message = await extractApiErrorMessage(error, CREATE_FAILED);
            if (currentRun?.controller !== controller) return null;
            currentRun = null;
            set({ messages: restore, isRunning: false, error: message });
            return null;
        }
        // 作成を待つ間に停止された、または別のチャットへ移った
        if (currentRun?.controller !== controller) {
            discardSession(detail.id);
            return null;
        }
        currentRun = { controller, restore, posted: true };
        const item = aggregateFromDetail(detail);
        set((state) => ({
            activeSessionId: item.id,
            activeSession: item,
            sessions: [item, ...state.sessions],
            sessionsCount: state.sessionsCount + 1,
            sessionsOffset: state.sessionsOffset + 1,
        }));
        hooks.onSessionCreated?.(item.id);
        return item.id;
    };

    return {
        ...initialState,

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

        loadConfigs: async () => {
            configsToken += 1;
            const token = configsToken;
            try {
                const configs = await apiFetchConfigs();
                if (token !== configsToken) return;
                const remembered = readSelectedConfig();
                const selected =
                    configs.find((c) => c.name === remembered) ?? configs[0];
                set({
                    configs,
                    selectedConfigName: selected?.name ?? null,
                    configsFailed: false,
                });
            } catch {
                if (token !== configsToken) return;
                set({ configsFailed: true });
            }
        },

        selectConfig: (name) => {
            writeSelectedConfig(name);
            set({ selectedConfigName: name });
        },

        openSession: async (id) => {
            if (get().activeSessionId === id) return 'ok';
            leaveThread();
            const token = openToken;
            set({
                ...emptyThread(),
                activeSessionId: id,
                isLoadingDetail: true,
            });
            try {
                const detail = await apiGetSession(id);
                if (token !== openToken) return 'stale';
                const item = aggregateFromDetail(detail);
                set((state) => ({
                    activeSession: item,
                    messages: detail.messages.map(fromServerMessage),
                    isLoadingDetail: false,
                    sessions: state.sessions.map((s) =>
                        s.id === id ? item : s,
                    ),
                }));
                return 'ok';
            } catch (error) {
                if (token !== openToken) return 'stale';
                if (isNotFound(error)) {
                    set(emptyThread());
                    return 'not-found';
                }
                set({
                    isLoadingDetail: false,
                    error: 'チャットの読み込みに失敗しました',
                });
                return 'error';
            }
        },

        startNewChat: () => {
            if (get().activeSessionId === null) return;
            leaveThread();
            set(emptyThread());
        },

        updateActiveTitle: async (title) => {
            const id = get().activeSessionId;
            if (!id) return;
            const detail = await apiUpdateSessionTitle(id, title);
            patchSession(id, { title: detail.title });
        },

        removeSession: async (id) => {
            await apiDeleteSession(id);
            backgroundRuns.forEach((sessionId, controller) => {
                if (sessionId === id) controller.abort(LEAVE);
            });
            if (get().activeSessionId === id) {
                leaveThread();
                set(emptyThread());
            }
            dropFromList(id);
        },

        sendMessage: async (content, hooks = {}) => {
            const state = get();
            if (state.isRunning || selectIsSendDisabled(state)) {
                return 'not-sent';
            }
            const controller = new AbortController();
            const restore = state.messages;
            const user = createUserMessage(content);
            const threadKey = state.threadKey;
            const createdSession = state.activeSessionId === null;
            currentRun = { controller, restore, posted: !createdSession };
            set({ messages: [...restore, user], isRunning: true, error: null });

            const sessionId =
                state.activeSessionId ??
                (await createSessionForRun(
                    controller,
                    state.selectedConfigName ?? '',
                    restore,
                    hooks,
                ));
            if (sessionId === null) return 'not-sent';

            return consumeTurn(
                {
                    controller,
                    sessionId,
                    threadKey,
                    restore,
                    userLocalId: user.localId,
                    assistantLocalId: createLocalId(),
                    createdSession,
                    hooks,
                    isSaved: (detail) =>
                        detail.messages.length > restore.length,
                },
                apiStreamMessage(sessionId, content, {
                    signal: controller.signal,
                }),
            );
        },

        editMessage: async (localId, content) => {
            const state = get();
            const sessionId = state.activeSessionId;
            const target = state.messages.find((m) => m.localId === localId);
            if (
                state.isRunning ||
                state.isSyncing ||
                state.isLoadingDetail ||
                sessionId === null ||
                target === undefined
            ) {
                return 'not-sent';
            }
            if (target.id === null) {
                set({ error: UNSAVED_MESSAGE });
                return 'not-sent';
            }
            const controller = new AbortController();
            const restore = state.messages;
            currentRun = { controller, restore, posted: true };
            set({
                messages: replaceFromTarget(restore, localId, content),
                isRunning: true,
                error: null,
            });

            return consumeTurn(
                {
                    controller,
                    sessionId,
                    threadKey: state.threadKey,
                    restore,
                    userLocalId: localId,
                    assistantLocalId: createLocalId(),
                    createdSession: false,
                    hooks: {},
                    isSaved: (detail) =>
                        detail.messages.find(
                            (m) => m.sequence === target.sequence,
                        )?.id !== target.id,
                },
                apiStreamEdit(sessionId, target.id, content, {
                    signal: controller.signal,
                }),
            );
        },

        regenerate: async (userLocalId) => {
            const target = get().messages.find(
                (m) => m.localId === userLocalId,
            );
            if (target) await get().editMessage(userLocalId, target.content);
        },

        cancelRun: () => {
            const run = currentRun;
            if (!run) return;
            currentRun = null;
            run.controller.abort(STOP);
            set(
                run.posted
                    ? (state) => ({
                          isRunning: false,
                          isSyncing: true,
                          messages: markCancelled(state.messages),
                      })
                    : { isRunning: false, messages: run.restore },
            );
        },

        deleteMessageAudio: async (messageId) => {
            const sessionId = get().activeSessionId;
            if (!sessionId) return;
            await apiDeleteAudio(sessionId, messageId);
            set((state) => withoutAudioIds(state, [messageId]));
            updateMessages(sessionId, (messages) =>
                clearAudio(messages, (m) => m.id === messageId),
            );
            patchSession(sessionId, {
                total_audio_bytes: totalAudioBytes(get().messages),
            });
        },

        deleteAllAudio: async () => {
            const sessionId = get().activeSessionId;
            if (!sessionId) return;
            await apiBulkDeleteAudio(sessionId);
            set((state) =>
                withoutAudioIds(state, [...state.audioObjectUrls.keys()]),
            );
            updateMessages(sessionId, (messages) =>
                clearAudio(messages, () => true),
            );
            patchSession(sessionId, { total_audio_bytes: 0 });
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
                .finally(() => pendingAudio.delete(messageId));
            pendingAudio.set(messageId, task);
            return task;
        },

        clearError: () => set({ error: null }),

        reset: () => {
            leaveThread();
            backgroundRuns.forEach((_sessionId, controller) => {
                controller.abort(LEAVE);
            });
            backgroundRuns.clear();
            pendingAudio.clear();
            listToken += 1;
            configsToken += 1;
            set({ ...initialState, ...emptyThread() });
        },
    };
});
