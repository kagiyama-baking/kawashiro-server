import { LogOut, Menu, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { NavLink, useNavigate } from 'react-router';
import swirlMark from '@/assets/swirl.webp';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useAuthStore } from '@/stores/auth-store';
import { navItems } from './nav-items';

// 暗い緑の面。フォーカスの枠は、この面の上でも見える明るい緑に切り替える
const SURFACE =
    'bg-sidebar text-sidebar-foreground [--ring:var(--sidebar-ring)]';

// ghost の hover（accent）はこの面と同じ色で見えないので上書きする
const GHOST_ON_SURFACE =
    'text-sidebar-muted-foreground hover:bg-sidebar-hover hover:text-sidebar-accent-foreground';

function Brand() {
    return (
        <div className="flex min-w-0 items-center gap-3">
            <img
                src={swirlMark}
                alt=""
                width={34}
                height={34}
                className="size-[34px] shrink-0 opacity-96"
            />
            <p className="text-sidebar-accent-foreground min-w-0 text-[1.02rem] leading-[1.15] font-semibold tracking-[0.06em]">
                鍵山製パン
                <small className="font-latin text-sidebar-muted-foreground mt-1.5 block text-[0.58rem] font-light tracking-[0.34em] uppercase">
                    Web App
                </small>
            </p>
        </div>
    );
}

function SidebarContent({ onClose }: { readonly onClose?: () => void }) {
    const email = useAuthStore((s) => s.email);
    const clearAuth = useAuthStore((s) => s.clearAuth);
    const navigate = useNavigate();

    const handleLogout = () => {
        clearAuth();
        navigate('/login', { replace: true });
    };

    return (
        <div className="flex h-full flex-col gap-[2.4rem] overflow-y-auto pt-[1.7rem] pb-[1.2rem] select-none">
            <div className="flex items-center justify-between gap-2 px-[1.4rem]">
                <Brand />
                {onClose && (
                    <Button
                        variant="ghost"
                        size="icon-sm"
                        onClick={onClose}
                        className={GHOST_ON_SURFACE}
                        aria-label="メニューを閉じる"
                    >
                        <X className="h-5 w-5" />
                    </Button>
                )}
            </div>

            <nav aria-label="メインメニュー">
                <ul className="flex flex-col gap-0.5 px-[0.7rem]">
                    {navItems.map(({ to, en, label }) => (
                        <li key={to}>
                            <NavLink
                                to={to}
                                end={to === '/'}
                                onClick={onClose}
                                className="text-sidebar-muted-foreground before:bg-sidebar-primary hover:bg-sidebar-hover hover:text-sidebar-accent-foreground aria-[current=page]:bg-sidebar-accent aria-[current=page]:text-sidebar-accent-foreground relative flex w-full flex-col items-start gap-[3px] rounded-md py-[0.7rem] pr-[0.8rem] pl-4 transition-colors before:absolute before:top-1/2 before:left-0 before:h-0 before:w-0.5 before:-translate-y-1/2 before:transition-[height] before:content-[''] aria-[current=page]:before:h-[62%]"
                            >
                                <span className="font-latin text-[0.76rem] tracking-[0.22em] uppercase">
                                    {en}
                                </span>
                                <span className="text-[0.66rem] tracking-[0.1em] opacity-78">
                                    {label}
                                </span>
                            </NavLink>
                        </li>
                    ))}
                </ul>
            </nav>

            <div className="border-sidebar-border mx-[1.4rem] mt-auto border-t pt-4">
                <p className="font-latin text-sidebar-muted-foreground truncate text-[0.7rem] tracking-[0.06em] select-text">
                    {email}
                </p>
                <Button
                    variant="ghost"
                    size="sm"
                    className={cn(
                        GHOST_ON_SURFACE,
                        'mt-2 -ml-[0.7rem] justify-start',
                    )}
                    onClick={handleLogout}
                >
                    <LogOut />
                    ログアウト
                </Button>
            </div>
        </div>
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
            {/* モバイルの上端バー */}
            <header
                className={cn(
                    SURFACE,
                    'flex h-(--mobile-bar-height) shrink-0 items-center gap-2 px-2 lg:hidden',
                )}
            >
                <Button
                    variant="ghost"
                    size="icon"
                    className={GHOST_ON_SURFACE}
                    onClick={() => setMobileOpen(true)}
                    aria-label="メニューを開く"
                >
                    <Menu className="h-5 w-5" />
                </Button>
                <Brand />
            </header>

            {/* モバイルオーバーレイ */}
            {mobileOpen && (
                <div
                    className="bg-overlay fixed inset-0 z-40 backdrop-blur-[4px] lg:hidden"
                    onClick={() => setMobileOpen(false)}
                    role="presentation"
                />
            )}

            {/* モバイルサイドバー。閉じている間は画面外のリンクにフォーカスさせない */}
            <aside
                inert={!mobileOpen}
                className={cn(
                    SURFACE,
                    'fixed inset-y-0 left-0 z-50 flex w-(--sidebar-width) flex-col transition-transform lg:hidden',
                    mobileOpen ? 'translate-x-0' : '-translate-x-full',
                )}
            >
                <SidebarContent onClose={() => setMobileOpen(false)} />
            </aside>

            {/* デスクトップサイドバー */}
            <aside
                className={cn(
                    SURFACE,
                    'hidden h-full w-(--sidebar-width) shrink-0 flex-col lg:flex',
                )}
            >
                <SidebarContent />
            </aside>
        </>
    );
}
