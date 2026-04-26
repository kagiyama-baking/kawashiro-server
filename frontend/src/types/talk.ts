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

export const CHAT_MESSAGE_MAX_LENGTH = 4000;
export const CHAT_HISTORY_MAX_COUNT = 50;
export const SESSION_LIST_DEFAULT_LIMIT = 20;
