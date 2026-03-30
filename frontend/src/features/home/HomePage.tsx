import { NavLink } from 'react-router';
import { navItems } from '@/components/layout/nav-items';
import { cn } from '@/lib/utils';

export function HomePage() {
    const menuItems = navItems.filter((item) => item.to !== '/');

    return (
        <div className="mx-auto max-w-4xl space-y-6">
            {/* ヒーローセクション — CSS生成アート */}
            <div className="glass neon-border relative overflow-hidden rounded-2xl">
                <div className="relative flex min-h-[200px] items-end sm:min-h-[260px] lg:min-h-[300px]">
                    {/* 浮遊オーブ */}
                    <div className="absolute inset-0 overflow-hidden">
                        <div className="animate-float-orb absolute -top-20 -right-20 h-60 w-60 rounded-full bg-[oklch(0.82_0.18_192/0.15)] blur-3xl" />
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
                                    'linear-gradient(oklch(0.82 0.18 192) 1px, transparent 1px), linear-gradient(90deg, oklch(0.82 0.18 192) 1px, transparent 1px)',
                                backgroundSize: '40px 40px',
                            }}
                        />
                    </div>
                    {/* テキストオーバーレイ */}
                    <div className="relative z-10 w-full p-8 sm:p-10">
                        <p className="mb-3 font-mono text-xs font-medium tracking-[0.2em] text-[oklch(0.82_0.18_192)] uppercase">
                            // KAGIYAMA BAKERY
                        </p>
                        <h1 className="font-heading text-foreground text-3xl font-extrabold tracking-tight sm:text-4xl lg:text-5xl">
                            鍵山製パン
                            <span className="neon-text">WebApp</span>
                        </h1>
                        <div className="mt-3 h-1 w-20 rounded-full bg-gradient-to-r from-[oklch(0.82_0.18_192)] via-[oklch(0.72_0.20_155)] to-transparent" />
                    </div>
                </div>
            </div>

            {/* メニューカード */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {menuItems.map(({ to, label, icon: Icon }, index) => (
                    <NavLink key={to} to={to} className="group">
                        <div
                            className="animate-slide-up"
                            style={{
                                animationDelay: `${index * 80}ms`,
                            }}
                        >
                            <div
                                className={cn(
                                    'glass neon-border flex items-center gap-5 rounded-xl p-5 transition-all duration-300',
                                    'hover:bg-[oklch(0.95_0_0/0.06)] hover:shadow-[0_0_20px_oklch(0.82_0.18_192/0.1)]',
                                )}
                            >
                                <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-[oklch(0.82_0.18_192/0.1)] text-[oklch(0.82_0.18_192)] transition-all duration-300 group-hover:bg-[oklch(0.82_0.18_192/0.2)] group-hover:shadow-[0_0_12px_oklch(0.82_0.18_192/0.3)]">
                                    <Icon className="h-5 w-5" />
                                </div>
                                <div className="space-y-1">
                                    <p className="text-sm font-semibold tracking-tight">
                                        {label}
                                    </p>
                                    <p className="text-muted-foreground text-xs leading-relaxed">
                                        {to === '/tts' &&
                                            'テキストを入力して音声を生成'}
                                        {to === '/talk' &&
                                            '設定に基づき会話テキスト生成＋読み上げ'}
                                        {to === '/media' &&
                                            '画像変換・ZIP→PDF変換'}
                                    </p>
                                </div>
                            </div>
                        </div>
                    </NavLink>
                ))}
            </div>
        </div>
    );
}
