import { useCallback, useEffect, useReducer, useRef } from 'react';
import { toast } from 'sonner';
import { fetchConfigs, sendChat } from '@/lib/api/talk';
import type {
    ChatMessageRequest,
    ChatMessageResult,
    GenerateConfig,
} from '@/types/talk';

interface ChatState {
    readonly configs: GenerateConfig[];
    readonly selectedConfig: string;
    readonly input: string;
    readonly messages: ChatMessageResult[];
    readonly isLoading: boolean;
    readonly error: string | null;
}

type ChatAction =
    | { type: 'SET_CONFIGS'; configs: GenerateConfig[] }
    | { type: 'SET_SELECTED_CONFIG'; config: string }
    | { type: 'SET_INPUT'; input: string }
    | { type: 'ADD_MESSAGE'; message: ChatMessageResult }
    | { type: 'SET_MESSAGE_ERROR'; id: string; errorMessage: string }
    | { type: 'TRUNCATE_FROM'; messageId: string }
    | { type: 'CLEAR_HISTORY' }
    | { type: 'SET_LOADING'; isLoading: boolean }
    | { type: 'SET_ERROR'; error: string | null };

const initialState: ChatState = {
    configs: [],
    selectedConfig: '',
    input: '',
    messages: [],
    isLoading: false,
    error: null,
};

function reducer(state: ChatState, action: ChatAction): ChatState {
    switch (action.type) {
        case 'SET_CONFIGS':
            return {
                ...state,
                configs: action.configs,
                selectedConfig:
                    state.selectedConfig || (action.configs[0]?.name ?? ''),
            };
        case 'SET_SELECTED_CONFIG':
            return { ...state, selectedConfig: action.config };
        case 'SET_INPUT':
            return { ...state, input: action.input };
        case 'ADD_MESSAGE':
            return { ...state, messages: [...state.messages, action.message] };
        case 'SET_MESSAGE_ERROR':
            return {
                ...state,
                messages: state.messages.map((m) =>
                    m.id === action.id
                        ? { ...m, errorMessage: action.errorMessage }
                        : m,
                ),
            };
        case 'TRUNCATE_FROM': {
            const idx = state.messages.findIndex(
                (m) => m.id === action.messageId,
            );
            if (idx < 0) return state;
            return { ...state, messages: state.messages.slice(0, idx) };
        }
        case 'CLEAR_HISTORY':
            return { ...state, messages: [], error: null };
        case 'SET_LOADING':
            return { ...state, isLoading: action.isLoading };
        case 'SET_ERROR':
            return { ...state, error: action.error };
    }
}

function makeId(): string {
    if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
        return crypto.randomUUID();
    }
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function useChat() {
    const [state, dispatch] = useReducer(reducer, initialState);
    const audioUrlsRef = useRef<Set<string>>(new Set());

    useEffect(() => {
        let cancelled = false;
        fetchConfigs()
            .then((configs) => {
                if (!cancelled) {
                    dispatch({ type: 'SET_CONFIGS', configs });
                }
            })
            .catch(() => {
                if (!cancelled) {
                    dispatch({
                        type: 'SET_ERROR',
                        error: '設定一覧の取得に失敗しました',
                    });
                }
            });
        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        const urls = audioUrlsRef.current;
        return () => {
            urls.forEach((url) => URL.revokeObjectURL(url));
            urls.clear();
        };
    }, []);

    const setSelectedConfig = useCallback((config: string) => {
        dispatch({ type: 'SET_SELECTED_CONFIG', config });
    }, []);

    const setInput = useCallback((input: string) => {
        dispatch({ type: 'SET_INPUT', input });
    }, []);

    const clearHistory = useCallback(() => {
        audioUrlsRef.current.forEach((url) => URL.revokeObjectURL(url));
        audioUrlsRef.current.clear();
        dispatch({ type: 'CLEAR_HISTORY' });
    }, []);

    const submitToApi = useCallback(
        async (history: ChatMessageResult[], userContent: string) => {
            const userMessage: ChatMessageResult = {
                id: makeId(),
                role: 'user',
                content: userContent,
                audioBlob: null,
                audioUrl: null,
                audioFormat: null,
                errorMessage: null,
            };
            dispatch({ type: 'ADD_MESSAGE', message: userMessage });
            dispatch({ type: 'SET_LOADING', isLoading: true });
            dispatch({ type: 'SET_ERROR', error: null });

            const apiMessages: ChatMessageRequest[] = [
                ...history.map((m) => ({ role: m.role, content: m.content })),
                { role: userMessage.role, content: userMessage.content },
            ];

            try {
                const response = await sendChat({
                    config_name: state.selectedConfig,
                    messages: apiMessages,
                });

                if (response.audioUrl) {
                    audioUrlsRef.current.add(response.audioUrl);
                }
                const assistantMessage: ChatMessageResult = {
                    id: makeId(),
                    role: 'assistant',
                    content: response.content,
                    audioBlob: response.audioBlob,
                    audioUrl: response.audioUrl,
                    audioFormat: response.audioFormat,
                    errorMessage: null,
                };
                dispatch({ type: 'ADD_MESSAGE', message: assistantMessage });
            } catch {
                dispatch({
                    type: 'SET_MESSAGE_ERROR',
                    id: userMessage.id,
                    errorMessage: '応答の生成に失敗しました',
                });
                dispatch({
                    type: 'SET_ERROR',
                    error: '応答の生成に失敗しました',
                });
                toast.error('チャット送信に失敗しました');
            } finally {
                dispatch({ type: 'SET_LOADING', isLoading: false });
            }
        },
        [state.selectedConfig],
    );

    const sendMessage = useCallback(async () => {
        if (!state.selectedConfig) return;
        const content = state.input;
        if (content.trim() === '') return;
        if (state.isLoading) return;

        dispatch({ type: 'SET_INPUT', input: '' });
        await submitToApi(state.messages, content);
    }, [
        state.selectedConfig,
        state.input,
        state.messages,
        state.isLoading,
        submitToApi,
    ]);

    const editAndResend = useCallback(
        async (messageId: string, newContent: string) => {
            if (!state.selectedConfig) return;
            if (newContent.trim() === '') return;
            if (state.isLoading) return;

            const idx = state.messages.findIndex((m) => m.id === messageId);
            if (idx < 0) return;

            // 編集対象以降のメッセージが持つ Object URL を解放
            for (let i = idx; i < state.messages.length; i++) {
                const url = state.messages[i].audioUrl;
                if (url) {
                    URL.revokeObjectURL(url);
                    audioUrlsRef.current.delete(url);
                }
            }

            const truncatedHistory = state.messages.slice(0, idx);
            dispatch({ type: 'TRUNCATE_FROM', messageId });
            await submitToApi(truncatedHistory, newContent);
        },
        [state.selectedConfig, state.messages, state.isLoading, submitToApi],
    );

    return {
        configs: state.configs,
        selectedConfig: state.selectedConfig,
        setSelectedConfig,
        input: state.input,
        setInput,
        messages: state.messages,
        isLoading: state.isLoading,
        error: state.error,
        sendMessage,
        editAndResend,
        clearHistory,
    } as const;
}
