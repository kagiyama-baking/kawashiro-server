import { describe, expect, it, vi, beforeEach } from 'vitest';

// api-client をテストする前にauth-storeをモック
vi.mock('@/stores/auth-store', () => {
    const state = {
        token: null as string | null,
        clearAuth: vi.fn(),
    };
    return {
        useAuthStore: {
            getState: () => state,
            __mockState: state,
        },
    };
});

// window.location.href をモック
const locationMock = { href: '' };
Object.defineProperty(window, 'location', {
    value: locationMock,
    writable: true,
});

describe('api-client', () => {
    beforeEach(() => {
        vi.resetModules();
        locationMock.href = '';
    });

    it('apiClient が ky インスタンスとしてエクスポートされる', async () => {
        const { apiClient } = await import('@/lib/api-client');
        expect(apiClient).toBeDefined();
    });
});
