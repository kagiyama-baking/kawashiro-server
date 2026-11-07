import { AssistantRuntimeProvider } from '@assistant-ui/react';
import { useEffect, useLayoutEffect } from 'react';
import { useNavigate, useParams } from 'react-router';
import { useChatStore } from '@/stores/chat-store';
import { ChatThread } from './ChatThread';
import { useChatRuntime } from './useChatRuntime';

function ChatRuntimeBoundary() {
    const runtime = useChatRuntime();
    return (
        <AssistantRuntimeProvider runtime={runtime}>
            <ChatThread />
        </AssistantRuntimeProvider>
    );
}

/** `/talk/:sessionId?`。URL が正で、ストアの表示中のセッションをそれに合わせる。 */
export function ChatPage() {
    const { sessionId } = useParams();
    const navigate = useNavigate();
    const threadKey = useChatStore((s) => s.threadKey);
    const loadSessions = useChatStore((s) => s.loadSessions);
    const loadSettings = useChatStore((s) => s.loadSettings);
    const openSession = useChatStore((s) => s.openSession);
    const startNewChat = useChatStore((s) => s.startNewChat);
    const reset = useChatStore((s) => s.reset);

    useEffect(() => {
        void loadSessions();
        void loadSettings();
        return () => reset();
    }, [loadSessions, loadSettings, reset]);

    // 新規チャットの画面が一瞬見えないよう、描画の前に読み込み中へ切り替える
    useLayoutEffect(() => {
        if (!sessionId) {
            startNewChat();
            return undefined;
        }
        let ignore = false;
        void openSession(sessionId).then((result) => {
            if (!ignore && result === 'not-found') {
                navigate('/talk', { replace: true });
            }
        });
        return () => {
            ignore = true;
        };
    }, [sessionId, openSession, startNewChat, navigate]);

    return <ChatRuntimeBoundary key={threadKey} />;
}
