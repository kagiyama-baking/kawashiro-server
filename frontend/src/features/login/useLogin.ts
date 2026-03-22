import { useState } from 'react';
import { useNavigate } from 'react-router';
import { login } from '@/lib/api/auth';
import { useAuthStore } from '@/stores/auth-store';

export function useLogin() {
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const setAuth = useAuthStore((s) => s.setAuth);
    const navigate = useNavigate();

    const handleLogin = async (email: string, password: string) => {
        setError(null);
        setIsLoading(true);

        try {
            const response = await login({ email, password });
            setAuth(response.token, email);
            navigate('/', { replace: true });
        } catch {
            setError(
                'ログインに失敗しました。メールアドレスまたはパスワードを確認してください。',
            );
        } finally {
            setIsLoading(false);
        }
    };

    return { error, isLoading, handleLogin } as const;
}
