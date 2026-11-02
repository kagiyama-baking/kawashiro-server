import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PageHeader } from '@/components/common/PageHeader';

describe('PageHeader', () => {
    it('タイトルを h1 として表示し、eyebrow は見出しの名前に含めない', () => {
        render(<PageHeader eyebrow="Voice" title="テキスト読み上げ" />);

        expect(screen.getByText('Voice')).toBeInTheDocument();
        expect(
            screen.getByRole('heading', {
                level: 1,
                name: 'テキスト読み上げ',
            }),
        ).toBeInTheDocument();
    });

    it('lead を渡すとリードを表示する', () => {
        render(
            <PageHeader
                eyebrow="Voice"
                title="テキスト読み上げ"
                lead="テキストを入力して音声を生成します"
            />,
        );

        expect(
            screen.getByText('テキストを入力して音声を生成します'),
        ).toBeInTheDocument();
    });

    it('lead を省略すると eyebrow と見出しだけを表示する', () => {
        const { container } = render(
            <PageHeader eyebrow="Voice" title="テキスト読み上げ" />,
        );

        expect(container.textContent).toBe('Voiceテキスト読み上げ');
    });
});
