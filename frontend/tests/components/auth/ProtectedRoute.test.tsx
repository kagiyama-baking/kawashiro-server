import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it } from 'vitest';
import { useAuthStore } from '@/stores/auth-store';
import { ProtectedRoute } from '@/components/auth/ProtectedRoute';

describe('ProtectedRoute', () => {
    beforeEach(() => {
        useAuthStore.setState({
            token: null,
            email: null,
            isAuthenticated: false,
        });
    });

    it('未認証の場合はログインページにリダイレクトされる', () => {
        const { container } = render(
            <MemoryRouter initialEntries={['/tts']}>
                <ProtectedRoute>
                    <div>保護されたコンテンツ</div>
                </ProtectedRoute>
            </MemoryRouter>,
        );

        expect(
            container.querySelector('[data-testid="protected-content"]'),
        ).toBeNull();
    });

    it('認証済みの場合は子コンポーネントが表示される', () => {
        useAuthStore.setState({
            token: 'test-token',
            email: 'user@example.com',
            isAuthenticated: true,
        });

        render(
            <MemoryRouter>
                <ProtectedRoute>
                    <div>保護されたコンテンツ</div>
                </ProtectedRoute>
            </MemoryRouter>,
        );

        expect(screen.getByText('保護されたコンテンツ')).toBeInTheDocument();
    });
});
