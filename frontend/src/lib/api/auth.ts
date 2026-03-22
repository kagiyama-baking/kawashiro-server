import type { LoginRequest, LoginResponse } from '@/types/auth';
import { apiClient } from '@/lib/api-client';

export async function login(credentials: LoginRequest): Promise<LoginResponse> {
    // DRFの ObtainAuthToken は username + password を期待する
    // カスタムUserモデルでは email をユーザー名として使用
    return apiClient
        .post('user/token/', {
            json: {
                username: credentials.email,
                password: credentials.password,
            },
        })
        .json<LoginResponse>();
}
