import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router';
import { PageHeader } from '@/components/common/PageHeader';
import { navItems } from '@/components/layout/nav-items';

const MENU_DESCRIPTIONS: Readonly<Record<string, string>> = {
    '/tts': 'テキストを入力して音声を生成',
    '/talk': '設定に基づき会話テキスト生成＋読み上げ',
    '/media': '画像変換・ZIP→PDF変換',
    '/pdf-edit': 'PDFのページを並び替え・削除・分割・トリミング',
};

export function HomePage() {
    const menuItems = navItems.filter((item) => item.to !== '/');

    return (
        <div className="max-w-(--page-max-width)">
            <PageHeader
                eyebrow="Home"
                title="鍵山製パンWebApp"
                lead="使う機能を選んでください"
            />
            {/* 4 枚が半端に折り返さないよう、列数は 1・2・4 で切り替える */}
            <ul className="grid gap-[clamp(1rem,1.6vw,1.4rem)] sm:grid-cols-2 xl:grid-cols-4">
                {menuItems.map(({ to, en, label }) => (
                    <li key={to}>
                        <Link
                            to={to}
                            className="group bg-card border-border hover:border-input hover:shadow-lift flex h-full flex-col overflow-hidden rounded-lg border transition-[translate,box-shadow,border-color] duration-400 hover:-translate-y-[5px] focus-visible:outline-offset-3"
                        >
                            {/* タイトルはカードの幅に合わせて縮める（最長の 8 文字でも表紙に収める） */}
                            <div className="bg-secondary text-ink-strong @container flex aspect-[16/10] flex-col items-center justify-center gap-[0.7rem] overflow-hidden p-[1.2rem] text-center">
                                <span className="font-latin pl-[0.32em] text-[0.66rem] font-light tracking-[0.32em] uppercase">
                                    {en}
                                </span>
                                <h2 className="text-[clamp(1.4rem,10cqi,2.1rem)] leading-[1.15] font-bold transition-transform duration-800 group-hover:scale-[1.04]">
                                    {label}
                                </h2>
                            </div>
                            <div className="flex flex-1 flex-col px-[1.3rem] pt-[1.2rem] pb-[1.4rem]">
                                <p className="text-muted-foreground text-[0.86rem] leading-[1.85]">
                                    {MENU_DESCRIPTIONS[to]}
                                </p>
                                <span className="text-primary mt-auto inline-flex items-center gap-[0.4rem] pt-[1.1rem] text-[0.84rem] font-medium tracking-[0.06em]">
                                    ひらく
                                    <ArrowRight className="size-4" />
                                </span>
                            </div>
                        </Link>
                    </li>
                ))}
            </ul>
        </div>
    );
}
