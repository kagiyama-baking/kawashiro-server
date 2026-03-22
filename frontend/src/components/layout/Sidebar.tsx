import { LogOut, Menu, X } from 'lucide-react';
import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/stores/auth-store';
import { navItems } from './nav-items';

function SidebarContent({ onClose }: { readonly onClose?: () => void }) {
    const email = useAuthStore((s) => s.email);
    const clearAuth = useAuthStore((s) => s.clearAuth);
    const navigate = useNavigate();

    const handleLogout = () => {
        clearAuth();
        navigate('/login', { replace: true });
    };

    return (
        <>
            <div className="flex items-center justify-between p-6">
                <h1 className="font-heading text-lg font-medium text-sidebar-foreground">
                    鍵山製パン
                </h1>
                {onClose && (
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={onClose}
                        className="lg:hidden"
                    >
                        <X className="h-5 w-5" />
                    </Button>
                )}
            </div>

            <Separator />

            <nav className="flex-1 space-y-1 p-3">
                {navItems.map(({ to, label, icon: Icon }) => (
                    <NavLink
                        key={to}
                        to={to}
                        end={to === '/'}
                        onClick={onClose}
                        className={({ isActive }) =>
                            cn(
                                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                                isActive
                                    ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                                    : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-foreground',
                            )
                        }
                    >
                        <Icon className="h-4 w-4" />
                        {label}
                    </NavLink>
                ))}
            </nav>

            <Separator />

            <div className="p-4">
                <p className="mb-2 truncate text-xs text-muted-foreground">
                    {email}
                </p>
                <Button
                    variant="ghost"
                    size="sm"
                    className="w-full justify-start gap-2"
                    onClick={handleLogout}
                >
                    <LogOut className="h-4 w-4" />
                    ログアウト
                </Button>
            </div>
        </>
    );
}

export function Sidebar() {
    const [mobileOpen, setMobileOpen] = useState(false);

    return (
        <>
            {/* モバイルハンバーガーボタン */}
            <Button
                variant="ghost"
                size="icon"
                className="fixed left-4 top-4 z-50 lg:hidden"
                onClick={() => setMobileOpen(true)}
            >
                <Menu className="h-5 w-5" />
            </Button>

            {/* モバイルオーバーレイ */}
            {mobileOpen && (
                <div
                    className="fixed inset-0 z-40 bg-black/50 lg:hidden"
                    onClick={() => setMobileOpen(false)}
                />
            )}

            {/* モバイルサイドバー */}
            <aside
                className={cn(
                    'fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-border bg-sidebar transition-transform duration-200 lg:hidden',
                    mobileOpen ? 'translate-x-0' : '-translate-x-full',
                )}
            >
                <SidebarContent onClose={() => setMobileOpen(false)} />
            </aside>

            {/* デスクトップサイドバー */}
            <aside className="hidden h-full w-64 flex-col border-r border-border bg-sidebar lg:flex">
                <SidebarContent />
            </aside>
        </>
    );
}
