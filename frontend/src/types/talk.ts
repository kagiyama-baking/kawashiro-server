export interface GenerateConfig {
    readonly name: string;
    readonly display_name: string;
    readonly tts_enabled: boolean;
}

export type ChatRole = 'user' | 'assistant';

// サーバから返るセッション詳細内のメッセージ
export interface ChatSessionMessage {
    readonly id: number;
    readonly sequence: number;
    readonly role: ChatRole;
    readonly content: string;
    readonly audio_url: string | null;
    readonly audio_format: string;
    readonly audio_size_bytes: number;
    readonly created_at: string;
}

export type ChatUiStatus = 'streaming' | 'complete' | 'cancelled';
export type ChatAudioState = 'idle' | 'pending' | 'failed';

// 画面に出す 1 メッセージ。送信中は id などのサーバー側の値がまだない
export interface ChatUiMessage {
    // 生涯変わらない識別子（`srv-<id>` か `local-<連番>`）。React の key になるので、
    // サーバー id が届いても置き換えない。置き換えると行がリマウントする。
    readonly localId: string;
    readonly id: number | null;
    readonly sequence: number | null;
    readonly role: ChatRole;
    readonly content: string;
    readonly audio_url: string | null;
    readonly audio_format: string;
    readonly audio_size_bytes: number;
    readonly created_at: string | null;
    readonly uiStatus: ChatUiStatus;
    readonly audioState: ChatAudioState;
    readonly audioError: string | null;
}

// セッション一覧の 1 項目
export interface ChatSessionListItem {
    readonly id: string;
    readonly title: string;
    readonly config_name: string;
    readonly message_count: number;
    readonly total_audio_bytes: number;
    readonly created_at: string;
    readonly updated_at: string;
}

// セッション詳細（messages 含む）
export interface ChatSessionDetail extends ChatSessionListItem {
    readonly messages: readonly ChatSessionMessage[];
}

// 一覧 API のレスポンス（DRF LimitOffsetPagination）
export interface ChatSessionListResponse {
    readonly count: number;
    readonly next: string | null;
    readonly previous: string | null;
    readonly results: readonly ChatSessionListItem[];
}

// メッセージ送信・編集の SSE イベント。type はイベント名に対応する
export type ChatStreamEvent =
    | { readonly type: 'start' }
    | { readonly type: 'delta'; readonly text: string }
    | {
          // 保存が済んだ。これ以降の切断では保存内容は変わらない
          readonly type: 'message';
          readonly user: ChatSessionMessage;
          readonly assistant: ChatSessionMessage;
      }
    | {
          readonly type: 'audio';
          readonly message_id: number;
          readonly audio_url: string;
          readonly audio_format: string;
          readonly audio_size_bytes: number;
      }
    | {
          readonly type: 'audio_error';
          readonly message_id: number;
          readonly error: string;
      }
    | { readonly type: 'title'; readonly title: string }
    | {
          // 終端。LLM の失敗で DB は変わっていない
          readonly type: 'error';
          readonly status: number;
          readonly error: string;
      }
    | {
          // 終端
          readonly type: 'done';
          readonly title: string;
          readonly message_count: number;
          readonly total_audio_bytes: number;
          readonly updated_at: string;
      };

export const CHAT_MESSAGE_MAX_LENGTH = 4000;
export const CHAT_HISTORY_MAX_COUNT = 50;
export const SESSION_LIST_DEFAULT_LIMIT = 20;
