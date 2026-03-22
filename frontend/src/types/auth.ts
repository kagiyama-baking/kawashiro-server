export interface LoginRequest {
    readonly email: string;
    readonly password: string;
}

export interface LoginResponse {
    readonly token: string;
    readonly user_id: number;
    readonly email: string;
}

export interface AuthState {
    readonly token: string | null;
    readonly email: string | null;
    readonly isAuthenticated: boolean;
}
