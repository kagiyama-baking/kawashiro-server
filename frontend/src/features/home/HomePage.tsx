import { ChevronRight } from 'lucide-react';
import { NavLink } from 'react-router';
import { navItems } from '@/components/layout/nav-items';
import { cn } from '@/lib/utils';

export function HomePage() {
    const menuItems = navItems.filter((item) => item.to !== '/');

    return (
        <div className="mx-auto max-w-4xl">
            {/* ヒーロー + メニュー統合セクション */}
            <div className="glass neon-border relative overflow-hidden rounded-2xl">
                {/* 浮遊オーブ */}
                <div className="absolute inset-0 overflow-hidden">
                    <div className="animate-float-orb absolute -top-20 -right-20 h-60 w-60 rounded-full bg-[oklch(0.75_0.20_155/0.15)] blur-3xl" />
                    <div
                        className="animate-float-orb absolute -bottom-10 -left-10 h-40 w-40 rounded-full bg-[oklch(0.72_0.20_155/0.12)] blur-3xl"
                        style={{ animationDelay: '-3s' }}
                    />
                    <div
                        className="animate-float-orb absolute top-10 left-1/3 h-32 w-32 rounded-full bg-[oklch(0.65_0.25_330/0.08)] blur-3xl"
                        style={{ animationDelay: '-5s' }}
                    />
                    {/* グリッドラインオーバーレイ */}
                    <div
                        className="absolute inset-0 opacity-[0.06]"
                        style={{
                            backgroundImage:
                                'linear-gradient(oklch(0.75 0.20 155) 1px, transparent 1px), linear-gradient(90deg, oklch(0.75 0.20 155) 1px, transparent 1px)',
                            backgroundSize: '40px 40px',
                        }}
                    />
                </div>

                {/* コンテンツ */}
                <div className="relative z-10 p-8 sm:p-10">
                    {/* タイトル部分 */}
                    <p className="mb-3 font-mono text-xs font-medium tracking-[0.2em] text-[oklch(0.75_0.20_155)] uppercase">
                        $ kagiyama-baking --version
                    </p>
                    <h1 className="font-heading text-foreground text-3xl font-extrabold tracking-tight sm:text-4xl lg:text-5xl">
                        鍵山製パン
                        <span className="neon-text">WebApp</span>
                    </h1>
                    <div className="mt-3 h-1 w-20 rounded-full bg-gradient-to-r from-[oklch(0.75_0.20_155)] via-[oklch(0.72_0.20_155)] to-transparent" />

                    {/* メニューリスト（ヒーロー内統合） */}
                    <nav className="mt-8 space-y-1">
                        {menuItems.map(({ to, label, icon: Icon }) => (
                            <NavLink key={to} to={to} className="group">
                                <div
                                    className={cn(
                                        'flex items-center gap-4 rounded-lg px-4 py-3 transition-all duration-200',
                                        'hover:bg-[oklch(0.75_0.20_155/0.08)]',
                                    )}
                                >
                                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[oklch(0.75_0.20_155/0.1)] text-[oklch(0.75_0.20_155)] transition-all duration-200 group-hover:bg-[oklch(0.75_0.20_155/0.2)] group-hover:shadow-[0_0_12px_oklch(0.75_0.20_155/0.3)]">
                                        <Icon className="h-4 w-4" />
                                    </div>
                                    <div className="flex-1">
                                        <p className="text-sm font-semibold tracking-tight">
                                            {label}
                                        </p>
                                        <p className="text-muted-foreground text-xs">
                                            {to === '/tts' &&
                                                'テキストを入力して音声を生成'}
                                            {to === '/talk' &&
                                                '設定に基づき会話テキスト生成＋読み上げ'}
                                            {to === '/media' &&
                                                '画像変換・ZIP→PDF変換'}
                                        </p>
                                    </div>
                                    <ChevronRight className="text-muted-foreground h-4 w-4 transition-transform duration-200 group-hover:translate-x-1 group-hover:text-[oklch(0.75_0.20_155)]" />
                                </div>
                            </NavLink>
                        ))}
                    </nav>
                </div>
            </div>
        </div>
    );
}
