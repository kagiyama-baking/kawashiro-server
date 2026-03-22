import ky from 'ky';
import { useAuthStore } from '@/stores/auth-store';

const baseUrl =
    typeof window !== 'undefined' && window.location.origin !== 'null'
        ? `${window.location.origin}/api`
        : 'http://localhost:5173/api';

function getCsrfToken(): string | null {
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : null;
}

export const apiClient = ky.create({
    prefixUrl: baseUrl,
    timeout: 120000,
    hooks: {
        beforeRequest: [
            (request) => {
                const { token } = useAuthStore.getState();
                if (token) {
                    request.headers.set('Authorization', `Token ${token}`);
                }
                // Django CSRF対策: CSRFトークンをヘッダーに付与
                const csrfToken = getCsrfToken();
                if (csrfToken) {
                    request.headers.set('X-CSRFToken', csrfToken);
                }
            },
        ],
        afterResponse: [
            (_request, _options, response) => {
                if (response.status === 401) {
                    useAuthStore.getState().clearAuth();
                    window.location.href = '/login';
                }
                return response;
            },
        ],
    },
});
