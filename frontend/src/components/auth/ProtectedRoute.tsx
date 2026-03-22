import type { ReactNode } from 'react';
import { Navigate } from 'react-router';
import { useAuthStore } from '@/stores/auth-store';

interface ProtectedRouteProps {
    readonly children: ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
    const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

    if (!isAuthenticated) {
        return <Navigate to="/login" replace />;
    }

    return <>{children}</>;
}
