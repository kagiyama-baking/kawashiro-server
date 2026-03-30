import { LogOut, Menu, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { NavLink, useNavigate } from 'react-router';
import { Button } from '@/components/ui/button';
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
            <div className="flex items-center justify-between px-5 py-5">
                <div>
                    <h1 className="font-heading neon-text text-lg font-bold tracking-tight">
                        鍵山製パン
                    </h1>
                    <div className="mt-2 h-px w-12 bg-gradient-to-r from-[oklch(0.75_0.20_155)] to-transparent" />
                </div>
                {onClose && (
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={onClose}
                        className="lg:hidden"
                        aria-label="メニューを閉じる"
                    >
                        <X className="h-5 w-5" />
                    </Button>
                )}
            </div>

            <nav className="flex-1 space-y-1 p-4">
                {navItems.map(({ to, label, icon: Icon }) => (
                    <NavLink
                        key={to}
                        to={to}
                        end={to === '/'}
                        onClick={(e) => {
                            e.currentTarget.blur();
                            onClose?.();
                        }}
                        className={({ isActive }) =>
                            cn(
                                'flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] font-medium transition-all duration-200',
                                isActive
                                    ? 'bg-[oklch(0.75_0.20_155/0.1)] text-[oklch(0.75_0.20_155)]'
                                    : 'hover:text-foreground text-[oklch(0.65_0.01_240)] hover:bg-[oklch(0.95_0_0/0.04)]',
                            )
                        }
                    >
                        <Icon className="h-4 w-4" />
                        {label}
                    </NavLink>
                ))}
            </nav>

            <div className="px-5 py-4">
                <p className="text-muted-foreground mb-3 truncate font-mono text-[11px] tracking-wide">
                    {email}
                </p>
                <Button
                    variant="ghost"
                    size="sm"
                    className="text-muted-foreground w-full justify-start gap-2 hover:text-[oklch(0.75_0.20_155)]"
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

    useEffect(() => {
        if (!mobileOpen) return;
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === 'Escape') setMobileOpen(false);
        };
        document.addEventListener('keydown', handleKeyDown);
        return () => document.removeEventListener('keydown', handleKeyDown);
    }, [mobileOpen]);

    return (
        <>
            {/* モバイルハンバーガーボタン */}
            <Button
                variant="ghost"
                size="icon"
                className="fixed top-4 left-4 z-50 lg:hidden"
                onClick={() => setMobileOpen(true)}
                aria-label="メニューを開く"
            >
                <Menu className="h-5 w-5" />
            </Button>

            {/* モバイルオーバーレイ */}
            {mobileOpen && (
                <div
                    className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm lg:hidden"
                    onClick={() => setMobileOpen(false)}
                />
            )}

            {/* モバイルサイドバー */}
            <aside
                className={cn(
                    'glass fixed inset-y-0 left-0 z-50 flex w-60 flex-col border-r border-[oklch(0.95_0_0/0.06)] transition-transform duration-200 lg:hidden',
                    mobileOpen ? 'translate-x-0' : '-translate-x-full',
                )}
            >
                <SidebarContent onClose={() => setMobileOpen(false)} />
            </aside>

            {/* デスクトップサイドバー */}
            <aside className="glass hidden h-full w-60 flex-col border-r border-[oklch(0.95_0_0/0.06)] lg:flex">
                <SidebarContent />
            </aside>
        </>
    );
}
