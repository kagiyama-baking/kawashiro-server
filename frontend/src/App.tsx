import { useEffect } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router';
import { Toaster } from '@/components/ui/sonner';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';
import { AppLayout } from '@/components/layout/AppLayout';
import { ChatPage } from '@/features/talk/ChatPage';
import { GeneratePage } from '@/features/talk/GeneratePage';
import { HomePage } from '@/features/home/HomePage';
import { LoginPage } from '@/features/login/LoginPage';
import { MediaPage } from '@/features/media/MediaPage';
import { TtsPage } from '@/features/tts/TtsPage';
import { useAuthStore } from '@/stores/auth-store';

function App() {
    const loadAuth = useAuthStore((s) => s.loadAuth);
    const isInitialized = useAuthStore((s) => s.isInitialized);

    useEffect(() => {
        loadAuth();
    }, [loadAuth]);

    // 認証状態の復元が完了するまで空白を表示
    if (!isInitialized) {
        return null;
    }

    return (
        <BrowserRouter>
            <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route
                    element={
                        <ProtectedRoute>
                            <AppLayout />
                        </ProtectedRoute>
                    }
                >
                    <Route index element={<HomePage />} />
                    <Route path="/tts" element={<TtsPage />} />
                    <Route path="/talk" element={<GeneratePage />} />
                    <Route path="/talk/chat" element={<ChatPage />} />
                    <Route path="/media" element={<MediaPage />} />
                </Route>
            </Routes>
            <Toaster />
        </BrowserRouter>
    );
}

export default App;
