import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { PdfFileUploader } from '@/features/pdf-edit/components/PdfFileUploader';

const MB = 1024 * 1024;

function pdfFile(sizeBytes: number) {
    const file = new File(['%PDF'], 'sample.pdf', { type: 'application/pdf' });
    Object.defineProperty(file, 'size', { value: sizeBytes });
    return file;
}

function setup() {
    const onFileSelected = vi.fn();
    const { container } = render(
        <PdfFileUploader onFileSelected={onFileSelected} />,
    );
    const input = container.querySelector<HTMLInputElement>('#pdf-file')!;
    return { onFileSelected, input, user: userEvent.setup() };
}

describe('PdfFileUploader', () => {
    it('上限以下のファイルは確認せずに渡す', async () => {
        const { onFileSelected, input, user } = setup();
        const file = pdfFile(200 * MB);

        await user.upload(input, file);

        expect(onFileSelected).toHaveBeenCalledWith(file);
        expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    });

    it('上限を超えるファイルはサイズを示して確認を求め、まだ渡さない', async () => {
        const { onFileSelected, input, user } = setup();

        await user.upload(input, pdfFile(210 * MB));

        const dialog = screen.getByRole('alertdialog');
        expect(dialog).toHaveTextContent('210MB');
        expect(onFileSelected).not.toHaveBeenCalled();
    });

    it('続行するとファイルを渡して閉じる', async () => {
        const { onFileSelected, input, user } = setup();
        const file = pdfFile(210 * MB);

        await user.upload(input, file);
        await user.click(
            within(screen.getByRole('alertdialog')).getByRole('button', {
                name: '続行',
            }),
        );

        expect(onFileSelected).toHaveBeenCalledTimes(1);
        expect(onFileSelected).toHaveBeenCalledWith(file);
        expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    });

    it('キャンセルするとファイルを渡さず、同じファイルを選び直せるよう入力を空にする', async () => {
        const { onFileSelected, input, user } = setup();

        await user.upload(input, pdfFile(210 * MB));
        await user.click(
            within(screen.getByRole('alertdialog')).getByRole('button', {
                name: 'キャンセル',
            }),
        );

        expect(onFileSelected).not.toHaveBeenCalled();
        expect(input.value).toBe('');
        expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    });
});
