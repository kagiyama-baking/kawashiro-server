import {
    act,
    fireEvent,
    render,
    screen,
    waitFor,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useRef, useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';

function renderDialog(
    overrides: Partial<Parameters<typeof ConfirmDialog>[0]> = {},
) {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
        <ConfirmDialog
            open
            title="チャットを削除"
            confirmLabel="削除"
            onConfirm={onConfirm}
            onCancel={onCancel}
            {...overrides}
        >
            このチャットを削除します。よろしいですか？
        </ConfirmDialog>,
    );
    return { onConfirm, onCancel };
}

describe('ConfirmDialog', () => {
    it('open が false のときは何も表示しない', () => {
        renderDialog({ open: false });

        expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    });

    it('タイトルと説明で名付けられた alertdialog として表示する', () => {
        renderDialog();

        const dialog = screen.getByRole('alertdialog', {
            name: 'チャットを削除',
        });
        expect(dialog).toHaveAccessibleDescription(
            'このチャットを削除します。よろしいですか？',
        );
    });

    it('開いたときの初期フォーカスはキャンセルボタンに置く', async () => {
        renderDialog();

        await waitFor(() => {
            expect(
                screen.getByRole('button', { name: 'キャンセル' }),
            ).toHaveFocus();
        });
    });

    it('確定ボタンを押すと onConfirm だけを呼ぶ', async () => {
        const user = userEvent.setup();
        const { onConfirm, onCancel } = renderDialog();

        await user.click(screen.getByRole('button', { name: '削除' }));

        expect(onConfirm).toHaveBeenCalledTimes(1);
        expect(onCancel).not.toHaveBeenCalled();
    });

    it('キャンセルボタンを押すと onCancel だけを呼ぶ', async () => {
        const user = userEvent.setup();
        const { onConfirm, onCancel } = renderDialog();

        await user.click(screen.getByRole('button', { name: 'キャンセル' }));

        expect(onCancel).toHaveBeenCalledTimes(1);
        expect(onConfirm).not.toHaveBeenCalled();
    });

    it('Esc キーで onCancel を呼ぶ', async () => {
        const user = userEvent.setup();
        const { onConfirm, onCancel } = renderDialog();

        await user.keyboard('{Escape}');

        expect(onCancel).toHaveBeenCalledTimes(1);
        expect(onConfirm).not.toHaveBeenCalled();
    });

    it('ダイアログの外を押しても閉じない', async () => {
        const { onConfirm, onCancel } = renderDialog();
        // Radix は外側の pointerdown の監視を次のタスクで始めるので、それを待ってから押す
        await act(() => new Promise((resolve) => setTimeout(resolve, 0)));

        fireEvent.pointerDown(document.body);

        expect(onCancel).not.toHaveBeenCalled();
        expect(onConfirm).not.toHaveBeenCalled();
    });

    it('閉じたら開いたボタンへフォーカスを戻す', async () => {
        const user = userEvent.setup();

        function Harness() {
            const [open, setOpen] = useState(false);
            const opener = useRef<HTMLButtonElement>(null);
            return (
                <>
                    <button
                        ref={opener}
                        type="button"
                        onClick={() => setOpen(true)}
                    >
                        開く
                    </button>
                    <ConfirmDialog
                        open={open}
                        title="チャットを削除"
                        confirmLabel="削除"
                        onConfirm={() => setOpen(false)}
                        onCancel={() => setOpen(false)}
                    >
                        このチャットを削除します。
                    </ConfirmDialog>
                </>
            );
        }

        render(<Harness />);
        const opener = screen.getByRole('button', { name: '開く' });

        await user.click(opener);
        await user.click(screen.getByRole('button', { name: 'キャンセル' }));

        await waitFor(() => {
            expect(opener).toHaveFocus();
        });
    });

    it('destructive を指定すると確定ボタンを destructive で表示する', () => {
        renderDialog({ destructive: true });

        expect(screen.getByRole('button', { name: '削除' })).toHaveAttribute(
            'data-variant',
            'destructive',
        );
    });

    it('destructive を省略すると確定ボタンは既定の見た目になる', () => {
        renderDialog();

        expect(screen.getByRole('button', { name: '削除' })).toHaveAttribute(
            'data-variant',
            'default',
        );
    });
});
