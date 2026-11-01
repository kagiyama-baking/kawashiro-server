import type { ReactNode } from 'react';

interface PageHeaderProps {
    readonly eyebrow: string;
    readonly title: string;
    readonly lead?: ReactNode;
}

/** ページ見出し。kagiyama.net の様式（欧文の eyebrow ＋ 和文の見出し ＋ リード）。 */
export function PageHeader({ eyebrow, title, lead }: PageHeaderProps) {
    return (
        <header className="mb-[clamp(1.8rem,3.5vw,2.6rem)]">
            <p className="font-latin text-primary mb-3 text-[0.78rem] font-light tracking-[0.42em] uppercase">
                {eyebrow}
            </p>
            <h1 className="text-[clamp(1.7rem,2.6vw,2.2rem)]">{title}</h1>
            {lead && (
                <p className="text-muted-foreground mt-[0.8rem] text-[0.92rem] leading-[1.9] tracking-[0.02em]">
                    {lead}
                </p>
            )}
        </header>
    );
}
