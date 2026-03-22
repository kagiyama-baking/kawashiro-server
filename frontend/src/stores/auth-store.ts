import { create } from 'zustand';

interface AuthStore {
    readonly token: string | null;
    readonly email: string | null;
    readonly isAuthenticated: boolean;
    readonly isInitialized: boolean;
    readonly setAuth: (token: string, email: string) => void;
    readonly clearAuth: () => void;
    readonly loadAuth: () => void;
}

export const useAuthStore = create<AuthStore>((set) => ({
    token: null,
    email: null,
    isAuthenticated: false,
    isInitialized: false,

    setAuth: (token: string, email: string) => {
        localStorage.setItem('auth-token', token);
        localStorage.setItem('auth-email', email);
        set({ token, email, isAuthenticated: true });
    },

    clearAuth: () => {
        localStorage.removeItem('auth-token');
        localStorage.removeItem('auth-email');
        set({ token: null, email: null, isAuthenticated: false });
    },

    loadAuth: () => {
        const token = localStorage.getItem('auth-token');
        const email = localStorage.getItem('auth-email');
        if (token) {
            set({ token, email, isAuthenticated: true, isInitialized: true });
        } else {
            set({ isInitialized: true });
        }
    },
}));
