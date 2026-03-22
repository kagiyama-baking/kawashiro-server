import { NavLink } from 'react-router';
import { navItems } from '@/components/layout/nav-items';
import { Card, CardDescription, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

// バナー画像のパス（public/banner.jpg に差し替え可能）
const BANNER_IMAGE = '/banner.jpg';

export function HomePage() {
    const menuItems = navItems.filter((item) => item.to !== '/');

    return (
        <div className="mx-auto max-w-5xl space-y-8">
            {/* バナーエリア */}
            <div className="relative overflow-hidden rounded-xl border border-border bg-card">
                <div className="relative flex min-h-[200px] items-end sm:min-h-[280px] lg:min-h-[320px]">
                    {/* 画像がない場合のフォールバック背景（画像があれば隠れる） */}
                    <div className="absolute inset-0 bg-gradient-to-br from-muted via-card to-background" />
                    {/* バナー背景画像（フォールバックの上に配置） */}
                    <img
                        src={BANNER_IMAGE}
                        alt=""
                        className="absolute inset-0 z-[1] h-full w-full object-cover"
                        onError={(e) => {
                            e.currentTarget.style.display = 'none';
                        }}
                    />
                    {/* テキスト読み取り用の下部グラデーション */}
                    <div className="relative z-[2] w-full bg-gradient-to-t from-background/95 via-background/60 to-transparent p-6 sm:p-8">
                        <h1 className="font-heading text-2xl font-medium tracking-tight text-foreground sm:text-3xl lg:text-4xl">
                            鍵山製パンWebApp
                        </h1>
                        <p className="mt-2 text-sm text-muted-foreground sm:text-base">
                            鍵山製パンの統合Webアプリケーション
                        </p>
                    </div>
                </div>
            </div>

            {/* メニューカード */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {menuItems.map(({ to, label, icon: Icon }) => (
                    <NavLink key={to} to={to} className="group">
                        <Card
                            className={cn(
                                'flex items-center gap-4 p-5 transition-all duration-200',
                                'hover:border-primary/50 hover:bg-accent/30 hover:shadow-md',
                            )}
                        >
                            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary/20">
                                <Icon className="h-6 w-6" />
                            </div>
                            <div>
                                <CardTitle className="font-sans text-base">
                                    {label}
                                </CardTitle>
                                <CardDescription className="text-xs">
                                    {to === '/tts' &&
                                        'テキストを入力して音声を生成'}
                                    {to === '/generate' &&
                                        'プロンプトからテキスト生成＋読み上げ'}
                                    {to === '/media' &&
                                        '画像変換・ZIP→PDF変換'}
                                </CardDescription>
                            </div>
                        </Card>
                    </NavLink>
                ))}
            </div>
        </div>
    );
}
