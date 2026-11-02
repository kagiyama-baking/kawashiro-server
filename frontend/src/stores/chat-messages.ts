import type {
    ChatRole,
    ChatSessionDetail,
    ChatSessionListItem,
    ChatSessionMessage,
    ChatUiMessage,
} from '@/types/talk';

type Messages = readonly ChatUiMessage[];

let localIdCounter = 0;

// crypto.randomUUID は安全なコンテキストでしか使えない。ページ内で一意なら足りる
export function createLocalId(): string {
    localIdCounter += 1;
    return `local-${localIdCounter}`;
}

function blankMessage(
    localId: string,
    role: ChatRole,
    content: string,
): ChatUiMessage {
    return {
        localId,
        id: null,
        sequence: null,
        role,
        content,
        audio_url: null,
        audio_format: '',
        audio_size_bytes: 0,
        created_at: null,
        uiStatus: 'complete',
        audioState: 'idle',
        audioError: null,
    };
}

export function fromServerMessage(message: ChatSessionMessage): ChatUiMessage {
    return {
        ...message,
        localId: `srv-${message.id}`,
        uiStatus: 'complete',
        audioState: 'idle',
        audioError: null,
    };
}

export function createUserMessage(content: string): ChatUiMessage {
    return blankMessage(createLocalId(), 'user', content);
}

function mapById(
    messages: Messages,
    messageId: number,
    update: (message: ChatUiMessage) => ChatUiMessage,
): Messages {
    return messages.map((m) => (m.id === messageId ? update(m) : m));
}

/** ストリームの差分を足す。空の assistant を先に作らないよう、行は最初の差分で追加する。 */
export function appendDelta(
    messages: Messages,
    assistantLocalId: string,
    text: string,
): Messages {
    if (!messages.some((m) => m.localId === assistantLocalId)) {
        return [
            ...messages,
            {
                ...blankMessage(assistantLocalId, 'assistant', text),
                uiStatus: 'streaming',
            },
        ];
    }
    return messages.map((m) =>
        m.localId === assistantLocalId
            ? { ...m, content: m.content + text }
            : m,
    );
}

interface SavedTurn {
    readonly userLocalId: string;
    readonly assistantLocalId: string;
    readonly user: ChatSessionMessage;
    readonly assistant: ChatSessionMessage;
    readonly audioPending: boolean;
}

/** 保存の通知を反映する。localId は変えないので行はリマウントしない。 */
export function applySaved(messages: Messages, saved: SavedTurn): Messages {
    const assistant: ChatUiMessage = {
        ...fromServerMessage(saved.assistant),
        localId: saved.assistantLocalId,
        audioState: saved.audioPending ? 'pending' : 'idle',
    };
    const next = messages.map((m) => {
        if (m.localId === saved.userLocalId) {
            return {
                ...m,
                id: saved.user.id,
                sequence: saved.user.sequence,
                content: saved.user.content,
                created_at: saved.user.created_at,
            };
        }
        return m.localId === saved.assistantLocalId ? assistant : m;
    });
    return next.some((m) => m.localId === saved.assistantLocalId)
        ? next
        : [...next, assistant];
}

interface AudioFields {
    readonly message_id: number;
    readonly audio_url: string;
    readonly audio_format: string;
    readonly audio_size_bytes: number;
}

export function applyAudio(messages: Messages, audio: AudioFields): Messages {
    return mapById(messages, audio.message_id, (m) => ({
        ...m,
        audio_url: audio.audio_url,
        audio_format: audio.audio_format,
        audio_size_bytes: audio.audio_size_bytes,
        audioState: 'idle',
        audioError: null,
    }));
}

export function applyAudioError(
    messages: Messages,
    messageId: number,
    error: string,
): Messages {
    return mapById(messages, messageId, (m) => ({
        ...m,
        audioState: 'failed',
        audioError: error,
    }));
}

export function clearAudio(
    messages: Messages,
    shouldClear: (message: ChatUiMessage) => boolean,
): Messages {
    return messages.map((m) =>
        shouldClear(m)
            ? {
                  ...m,
                  audio_url: null,
                  audio_format: '',
                  audio_size_bytes: 0,
                  audioState: 'idle',
                  audioError: null,
              }
            : m,
    );
}

/** 音声の通知が来ないまま終わった行の「合成中」を解く。 */
export function finishPendingAudio(messages: Messages): Messages {
    return messages.map((m) =>
        m.audioState === 'pending' ? { ...m, audioState: 'idle' } : m,
    );
}

export function markCancelled(messages: Messages): Messages {
    return messages.map((m) =>
        m.uiStatus === 'streaming' ? { ...m, uiStatus: 'cancelled' } : m,
    );
}

/** 編集の楽観表示。サーバーと同じく対象以降を落とす。id は保存の通知が来るまで元のまま。 */
export function replaceFromTarget(
    messages: Messages,
    targetLocalId: string,
    content: string,
): Messages {
    const index = messages.findIndex((m) => m.localId === targetLocalId);
    return [...messages.slice(0, index), { ...messages[index], content }];
}

/** サーバーの値へ同期する。位置で対応付けて localId を保つので行はリマウントしない。 */
export function mergeServerMessages(
    local: Messages,
    server: readonly ChatSessionMessage[],
): Messages {
    return server.map((message, index) => {
        const base = fromServerMessage(message);
        const current = local[index];
        if (current?.role !== message.role) return base;
        const isSameRow = current.id === message.id;
        const keepAudioState = isSameRow && message.audio_url === null;
        return {
            ...base,
            localId: current.localId,
            uiStatus:
                current.uiStatus === 'cancelled' ? 'cancelled' : 'complete',
            audioState: keepAudioState ? current.audioState : 'idle',
            audioError: keepAudioState ? current.audioError : null,
        };
    });
}

export function aggregateFromDetail(
    detail: ChatSessionDetail,
): ChatSessionListItem {
    return {
        id: detail.id,
        title: detail.title,
        config_name: detail.config_name,
        message_count: detail.messages.length,
        total_audio_bytes: detail.messages.reduce(
            (sum, m) => sum + m.audio_size_bytes,
            0,
        ),
        created_at: detail.created_at,
        updated_at: detail.updated_at,
    };
}
