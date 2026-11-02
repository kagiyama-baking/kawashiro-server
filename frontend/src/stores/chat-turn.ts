import { HTTPError } from 'ky';
import { extractApiErrorMessage } from '@/lib/api/errors';
import {
    createSession as apiCreateSession,
    deleteSession as apiDeleteSession,
    getSession as apiGetSession,
    streamEdit as apiStreamEdit,
    streamMessage as apiStreamMessage,
} from '@/lib/api/talk';
import type {
    ChatSessionDetail,
    ChatStreamEvent,
    ChatUiMessage,
} from '@/types/talk';
import {
    aggregateFromDetail,
    appendDelta,
    applyAudio,
    applyAudioError,
    applySaved,
    createLocalId,
    createUserMessage,
    finishPendingAudio,
    hasSameRows,
    markCancelled,
    replaceFromTarget,
    rollbackMessages,
} from './chat-messages';
import {
    type ChatStateUpdaters,
    type GetChatState,
    selectIsSendDisabled,
    type SetChatState,
    withoutAudioIds,
} from './chat-state';

/** 送信の結果。not-sent なら入力文を入力欄へ戻す（呼び出し側が MessageNotSentError にする）。 */
export type SendResult = 'sent' | 'not-sent';

/** 遅延作成したセッションの URL を呼び出し側で合わせるための通知。 */
export interface TurnHooks {
    readonly onSessionCreated?: (sessionId: string) => void;
    readonly onSessionAbandoned?: () => void;
}

const SYNC_INTERVAL_MS = 500;
const SYNC_TIMEOUT_MS = 10_000;

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
    readonly kind: 'send' | 'edit';
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

function delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function hasStatus(error: unknown, status: number): boolean {
    return error instanceof HTTPError && error.response.status === status;
}

function discardSession(sessionId: string): void {
    apiDeleteSession(sessionId).catch(() => {});
}

export interface ChatTurns {
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
}

/** ストアの外へは出さない、run の中断の操作。 */
export interface ChatTurnControls {
    readonly actions: ChatTurns;
    /** 本文を生成している run を中断する。音声とタイトルを待つ run は別のセッションを壊さないので止めない。 */
    readonly leaveCurrentRun: () => void;
    readonly abortBackgroundRuns: (sessionId?: string) => void;
}

/**
 * 送信と編集の 1 ターンを扱う。
 *
 * LLM の応答中はサーバーに何も保存されず、`message` イベントで保存が確定する。
 * - それより前の失敗: 楽観表示を戻す（`error` イベント、HTTP エラー、接続できない）
 * - それより前の停止と切断: サーバーが途中までを保存するので、GET で確かめて揃える
 * - 保存のあと: 生成中を解いて次を打てるようにし、音声とタイトルを裏で待つ
 */
export function createChatTurns(
    set: SetChatState,
    get: GetChatState,
    updaters: ChatStateUpdaters,
): ChatTurnControls {
    const {
        updateMessages,
        patchSession,
        moveSessionToTop,
        applyServerDetail,
        dropFromList,
    } = updaters;

    let currentRun: CurrentRun | null = null;
    // 保存が済み、音声とタイトルを待っている run（controller → セッション id）
    const backgroundRuns = new Map<AbortController, string>();

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
            case 'error':
                // 保存のあとのエラー。本文は残っているので知らせるだけにする
                if (get().activeSessionId === ctx.sessionId) {
                    set({ error: event.error });
                }
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
                if (hasStatus(error, 404)) return { status: 'gone' };
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

    /** サーバーの値を 1 度読み直す。次のターンの表示は巻き戻さない。 */
    const refreshFromServer = async (sessionId: string) => {
        try {
            const detail = await apiGetSession(sessionId);
            const state = get();
            if (
                state.activeSessionId === sessionId &&
                !state.isRunning &&
                !state.isSyncing
            ) {
                applyServerDetail(detail);
            }
        } catch {
            // 次の読み込みで揃う
        }
    };

    /** 保存のあと done の前に切れた。音声の通知は来ないので、保存された値を読み直す。 */
    const refreshAfterLostStream = async (ctx: TurnContext) => {
        updateMessages(ctx.sessionId, (messages) =>
            finishPendingAudio(messages, ctx.assistantLocalId),
        );
        await refreshFromServer(ctx.sessionId);
    };

    /** 応答が始まる前の失敗。サーバーの文言を出して楽観表示を戻す。 */
    const rejectTurn = async (
        ctx: TurnContext,
        error: unknown,
    ): Promise<SendResult> => {
        detachRun(ctx.controller);
        const message = await extractApiErrorMessage(error, SEND_FAILED);
        const result = failTurn(ctx, message);
        // 件数の上限なら、別のタブなどで増えた分を読み直して上限の案内を出す
        if (ctx.kind === 'send' && hasStatus(error, 400)) {
            void refreshFromServer(ctx.sessionId);
        }
        return result;
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
                if (event.type === 'error' && !saved) {
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
                return await rejectTurn(ctx, error);
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

    const actions: ChatTurns = {
        sendMessage: async (content, hooks = {}) => {
            const state = get();
            if (state.isRunning || selectIsSendDisabled(state)) {
                return 'not-sent';
            }
            const controller = new AbortController();
            const restore = state.messages;
            const user = createUserMessage(content);
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
                    kind: 'send',
                    controller,
                    sessionId,
                    threadKey: state.threadKey,
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
                    kind: 'edit',
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
            if (target) await actions.editMessage(userLocalId, target.content);
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
    };

    return {
        actions,
        leaveCurrentRun: () => {
            currentRun?.controller.abort(LEAVE);
            currentRun = null;
        },
        abortBackgroundRuns: (sessionId) => {
            backgroundRuns.forEach((runSessionId, controller) => {
                if (sessionId === undefined || runSessionId === sessionId) {
                    controller.abort(LEAVE);
                }
            });
        },
    };
}
