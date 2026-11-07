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
    settleOrphanedAudio,
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
const SESSION_GONE = 'このチャットは削除されています';

// 中断の理由。fetch は signal.reason でリジェクトするので AbortError の形にしておく
const STOP = new DOMException('ユーザーが停止した', 'AbortError');
// 別のチャットへ移った。サーバーは途中までを保存するので、裏で確かめて反映する
const SWITCH = new DOMException('別のチャットへ移った', 'AbortError');
// 画面を離れた、またはセッションを消した。もう確かめない
const CLOSE = new DOMException('チャットを閉じた', 'AbortError');

/** 本文を生成している run。保存が済むとここから外れて backgroundRuns へ移る。 */
interface CurrentRun {
    readonly controller: AbortController;
    readonly restore: readonly ChatUiMessage[];
    // セッションの作成を待っている間は false。まだ何も送っていないので同期が要らない
    readonly posted: boolean;
}

/** 保存が済み、音声とタイトルを待っている run。 */
interface BackgroundRun {
    readonly sessionId: string;
    readonly assistantLocalId: string;
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
        hooks?: TurnHooks,
    ) => Promise<SendResult>;
    readonly regenerate: (
        userLocalId: string,
        hooks?: TurnHooks,
    ) => Promise<void>;
    readonly cancelRun: () => void;
}

/** ストアの外へは出さない、run の中断の操作。 */
export interface ChatTurnControls {
    readonly actions: ChatTurns;
    /**
     * 別のチャットへ移るとき。本文を生成している run を中断し、保存を裏で確かめる。
     * 音声とタイトルを待つ run は別のセッションを壊さないので止めない。
     */
    readonly leaveForAnotherThread: () => void;
    /** セッションを消すとき。そのセッションの run を止める。 */
    readonly closeSessionRuns: (sessionId: string) => void;
    /** チャットの画面を離れるとき。すべての run と裏の確認を止める。 */
    readonly closeAllRuns: () => void;
}

/**
 * 送信と編集の 1 ターンを扱う。
 *
 * LLM の応答中はサーバーに何も保存されず、`message` イベントで保存が確定する。
 * - それより前の失敗: 楽観表示を戻す（`error` イベント、HTTP エラー、接続できない）
 * - それより前の停止と切断: サーバーが途中までを保存するので、GET で確かめて揃える
 * - 保存のあと: 生成中を解いて次を打てるようにし、音声とタイトルを裏で待つ
 *
 * `reloadSettings` は、新規チャットの作成を断られたときに Talk 設定の一覧と選択を読み直す。
 */
export function createChatTurns(
    set: SetChatState,
    get: GetChatState,
    updaters: ChatStateUpdaters,
    reloadSettings: () => Promise<void>,
): ChatTurnControls {
    const {
        updateMessages,
        patchSession,
        moveSessionToTop,
        applyServerDetail,
        dropFromList,
    } = updaters;

    let currentRun: CurrentRun | null = null;
    const backgroundRuns = new Map<AbortController, BackgroundRun>();
    // 履歴が動いたら増やす。読み直しの間に動いていたら、古い応答を捨てる
    let historyVersion = 0;
    // 画面を離れたら増やす。裏で続けている確認をやめる
    let closeEpoch = 0;

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
        const restored = rollbackMessages(
            ctx.restore,
            get().messages,
            ctx.userLocalId,
        );
        // 編集の間は行を落としていたので、音声の通知を受け取れなかった行があるかもしれない
        const waiting = new Set(
            [...backgroundRuns.values()].map((run) => run.assistantLocalId),
        );
        const settled = settleOrphanedAudio(restored, waiting);
        set({
            messages: settled,
            isRunning: false,
            isSyncing: false,
            error: message,
        });
        if (ctx.createdSession) {
            discardSession(ctx.sessionId);
            abandonSession(ctx);
        } else if (settled.some((m, index) => m !== restored[index])) {
            void refreshFromServer(ctx.sessionId);
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
        backgroundRuns.set(ctx.controller, {
            sessionId: ctx.sessionId,
            assistantLocalId: ctx.assistantLocalId,
        });
        historyVersion += 1;
        if (!isSameThread(ctx)) return;
        const state = get();
        const audioPending = state.activeSession?.tts_enabled ?? false;
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

    /**
     * 保存を確認するまで詳細を読み直す。ky の既定だと GET が固まったときに 2 分ほど待つので、
     * 残り時間だけ待って再試行しない。
     */
    const pollForSavedTurn = async (
        ctx: TurnContext,
        shouldContinue: () => boolean,
    ): Promise<SyncResult> => {
        const deadline = Date.now() + SYNC_TIMEOUT_MS;
        let latest: ChatSessionDetail | null = null;
        for (;;) {
            try {
                latest = await apiGetSession(ctx.sessionId, {
                    timeout: deadline - Date.now(),
                    retry: 0,
                });
                if (ctx.isSaved(latest)) {
                    return { status: 'saved', detail: latest };
                }
            } catch (error) {
                if (hasStatus(error, 404)) return { status: 'gone' };
            }
            if (Date.now() + SYNC_INTERVAL_MS >= deadline) {
                return { status: 'timeout', detail: latest };
            }
            await delay(SYNC_INTERVAL_MS);
            if (!shouldContinue()) {
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
        const result = await pollForSavedTurn(ctx, () => isSameThread(ctx));
        if (!isSameThread(ctx)) return 'sent';

        switch (result.status) {
            case 'saved':
                applyServerDetail(result.detail);
                set({ isSyncing: false });
                return 'sent';
            case 'gone':
                set({ isSyncing: false });
                abandonSession(ctx);
                set({ error: SESSION_GONE });
                return 'not-sent';
            default:
                return settleTimedOutSync(ctx, result.detail);
        }
    };

    /** 次のターンが動いていなければ、表示をサーバーの詳細へ揃える。 */
    const applyDetailIfIdle = (detail: ChatSessionDetail): boolean => {
        const state = get();
        const isIdle =
            state.activeSessionId === detail.id &&
            !state.isRunning &&
            !state.isSyncing &&
            !state.isLoadingDetail;
        if (isIdle) applyServerDetail(detail);
        return isIdle;
    };

    /** サーバーの値を 1 度読み直す。読み直しの間に履歴が動いていたら、古い応答は捨てる。 */
    async function refreshFromServer(sessionId: string): Promise<void> {
        const version = historyVersion;
        try {
            const detail = await apiGetSession(sessionId);
            if (version === historyVersion) applyDetailIfIdle(detail);
        } catch {
            // 次の読み込みで揃う
        }
    }

    /** 保存のあと done の前に切れた。音声の通知は来ないので、保存された値を読み直す。 */
    const refreshAfterLostStream = async (ctx: TurnContext) => {
        // 保存の通知を処理できなかった場合も、生成中のまま止まらないようにする
        if (isSameThread(ctx) && currentRun === null) {
            set({ isRunning: false });
        }
        updateMessages(ctx.sessionId, (messages) =>
            finishPendingAudio(messages, ctx.assistantLocalId),
        );
        await refreshFromServer(ctx.sessionId);
    };

    /** 生成中に別のチャットへ移ったターン。保存されるのを裏で確かめて一覧と表示に反映する。 */
    const syncLeftTurn = async (ctx: TurnContext) => {
        const epoch = closeEpoch;
        const result = await pollForSavedTurn(ctx, () => epoch === closeEpoch);
        if (result.status !== 'saved' || epoch !== closeEpoch) return;
        if (!applyDetailIfIdle(result.detail)) {
            patchSession(ctx.sessionId, aggregateFromDetail(result.detail));
        }
    };

    /** セッションが別のタブなどで消されていたら手放す。編集対象が消えた 404 と区別するため確かめる。 */
    const abandonIfGone = async (ctx: TurnContext) => {
        try {
            await apiGetSession(ctx.sessionId);
        } catch (error) {
            if (
                hasStatus(error, 404) &&
                isSameThread(ctx) &&
                get().activeSessionId === ctx.sessionId
            ) {
                abandonSession(ctx);
                set({ error: SESSION_GONE });
            }
        }
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
        if (hasStatus(error, 404) && !ctx.createdSession) {
            void abandonIfGone(ctx);
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
                    const result = failTurn(ctx, event.error);
                    if (event.status === 404 && !ctx.createdSession) {
                        void abandonIfGone(ctx);
                    }
                    return result;
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

        if (controller.signal.reason === CLOSE) return 'sent';
        if (controller.signal.reason === SWITCH) {
            void syncLeftTurn(ctx);
            return 'sent';
        }
        if (!saved) return syncInterruptedTurn(ctx);
        if (!finished) await refreshAfterLostStream(ctx);
        return 'sent';
    };

    /** 新規チャットの最初の送信で、選んだ Talk 設定とシーンのセッションを作る。使えなければ null を返す。 */
    const createSessionForRun = async (
        controller: AbortController,
        settingId: number,
        skillName: string | null,
        restore: readonly ChatUiMessage[],
        hooks: TurnHooks,
    ): Promise<string | null> => {
        const creating = apiCreateSession(settingId, skillName);
        const aborted = new Promise<null>((resolve) => {
            controller.signal.addEventListener('abort', () => resolve(null), {
                once: true,
            });
        });
        let detail: ChatSessionDetail | null;
        try {
            detail = await Promise.race([creating, aborted]);
        } catch (error) {
            const message = await extractApiErrorMessage(error, CREATE_FAILED);
            if (currentRun?.controller !== controller) return null;
            currentRun = null;
            set({ messages: restore, isRunning: false, error: message });
            // 選んだ Talk 設定やシーンが、画面を開いている間に使えなくなった。
            // 同じ選択のまま断られ続けないよう、一覧と選択を読み直す
            if (hasStatus(error, 400)) void reloadSettings();
            return null;
        }
        // 停止された、または別のチャットへ移った。応答を待たずに入力文を戻し、作られたら消す
        if (detail === null || currentRun?.controller !== controller) {
            creating.then(
                ({ id }) => discardSession(id),
                () => {},
            );
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
            historyVersion += 1;
            set({ messages: [...restore, user], isRunning: true, error: null });

            const sessionId =
                state.activeSessionId ??
                (await createSessionForRun(
                    controller,
                    // 新規チャットで送れるなら選ばれている（selectIsSendDisabled）
                    state.selectedSettingId ?? 0,
                    state.selectedSkillName,
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

        editMessage: async (localId, content, hooks = {}) => {
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
            historyVersion += 1;
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
                    hooks,
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

        regenerate: async (userLocalId, hooks) => {
            const target = get().messages.find(
                (m) => m.localId === userLocalId,
            );
            if (target) {
                await actions.editMessage(userLocalId, target.content, hooks);
            }
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

    const abortCurrentRun = (reason: DOMException) => {
        currentRun?.controller.abort(reason);
        currentRun = null;
    };

    return {
        actions,
        leaveForAnotherThread: () => abortCurrentRun(SWITCH),
        closeSessionRuns: (sessionId) => {
            if (get().activeSessionId === sessionId) abortCurrentRun(CLOSE);
            backgroundRuns.forEach((run, controller) => {
                if (run.sessionId === sessionId) controller.abort(CLOSE);
            });
        },
        closeAllRuns: () => {
            closeEpoch += 1;
            abortCurrentRun(CLOSE);
            backgroundRuns.forEach((_run, controller) => {
                controller.abort(CLOSE);
            });
        },
    };
}
