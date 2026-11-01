import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PageHeader } from '@/components/common/PageHeader';

describe('PageHeader', () => {
    it('タイトルをページの h1 として表示する', () => {
        render(<PageHeader eyebrow="Voice" title="テキスト読み上げ" />);

        expect(
            screen.getByRole('heading', {
                level: 1,
                name: 'テキスト読み上げ',
            }),
        ).toBeInTheDocument();
    });

    it('eyebrow を見出しの前に表示する', () => {
        render(<PageHeader eyebrow="Voice" title="テキスト読み上げ" />);

        const eyebrow = screen.getByText('Voice');
        const heading = screen.getByRole('heading', { level: 1 });
        expect(
            eyebrow.compareDocumentPosition(heading) &
                Node.DOCUMENT_POSITION_FOLLOWING,
        ).toBeTruthy();
    });

    it('eyebrow は見出しの名前に含めない', () => {
        render(<PageHeader eyebrow="Voice" title="テキスト読み上げ" />);

        expect(screen.getByRole('heading', { level: 1 })).not.toHaveTextContent(
            'Voice',
        );
    });

    it('lead を渡すと見出しの後ろにリードを表示する', () => {
        render(
            <PageHeader
                eyebrow="Voice"
                title="テキスト読み上げ"
                lead="テキストを入力して音声を生成します"
            />,
        );

        const lead = screen.getByText('テキストを入力して音声を生成します');
        const heading = screen.getByRole('heading', { level: 1 });
        expect(
            heading.compareDocumentPosition(lead) &
                Node.DOCUMENT_POSITION_FOLLOWING,
        ).toBeTruthy();
    });

    it('lead を省略するとリードの段落を出さない', () => {
        const { container } = render(
            <PageHeader eyebrow="Voice" title="テキスト読み上げ" />,
        );

        // eyebrow の段落だけが残る
        expect(container.querySelectorAll('p')).toHaveLength(1);
    });
});
