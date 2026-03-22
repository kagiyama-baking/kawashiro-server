import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuthStore } from '@/stores/auth-store';

const mockLocalStorage = (() => {
    let store: Record<string, string> = {};
    return {
        getItem: vi.fn((key: string) => store[key] ?? null),
        setItem: vi.fn((key: string, value: string) => {
            store[key] = value;
        }),
        removeItem: vi.fn((key: string) => {
            delete store[key];
        }),
        clear: vi.fn(() => {
            store = {};
        }),
    };
})();

Object.defineProperty(window, 'localStorage', { value: mockLocalStorage });

describe('auth-store', () => {
    beforeEach(() => {
        mockLocalStorage.clear();
        useAuthStore.setState({
            token: null,
            email: null,
            isAuthenticated: false,
            isInitialized: false,
        });
    });

    it('初期状態は未認証', () => {
        const state = useAuthStore.getState();
        expect(state.token).toBeNull();
        expect(state.email).toBeNull();
        expect(state.isAuthenticated).toBe(false);
    });

    it('setAuth でトークンとメールを保存する', () => {
        useAuthStore.getState().setAuth('test-token', 'user@example.com');

        const state = useAuthStore.getState();
        expect(state.token).toBe('test-token');
        expect(state.email).toBe('user@example.com');
        expect(state.isAuthenticated).toBe(true);
    });

    it('setAuth で localStorage に保存する', () => {
        useAuthStore.getState().setAuth('test-token', 'user@example.com');

        expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
            'auth-token',
            'test-token',
        );
        expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
            'auth-email',
            'user@example.com',
        );
    });

    it('clearAuth でトークンとメールをクリアする', () => {
        useAuthStore.getState().setAuth('test-token', 'user@example.com');
        useAuthStore.getState().clearAuth();

        const state = useAuthStore.getState();
        expect(state.token).toBeNull();
        expect(state.email).toBeNull();
        expect(state.isAuthenticated).toBe(false);
    });

    it('clearAuth で localStorage からも削除する', () => {
        useAuthStore.getState().setAuth('test-token', 'user@example.com');
        useAuthStore.getState().clearAuth();

        expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('auth-token');
        expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('auth-email');
    });

    it('loadAuth で localStorage から復元する', () => {
        mockLocalStorage.getItem.mockImplementation((key: string) => {
            if (key === 'auth-token') return 'saved-token';
            if (key === 'auth-email') return 'saved@example.com';
            return null;
        });

        useAuthStore.getState().loadAuth();

        const state = useAuthStore.getState();
        expect(state.token).toBe('saved-token');
        expect(state.email).toBe('saved@example.com');
        expect(state.isAuthenticated).toBe(true);
    });

    it('loadAuth で localStorage にトークンがない場合は未認証のまま', () => {
        mockLocalStorage.getItem.mockReturnValue(null);

        useAuthStore.getState().loadAuth();

        const state = useAuthStore.getState();
        expect(state.token).toBeNull();
        expect(state.isAuthenticated).toBe(false);
    });
});
