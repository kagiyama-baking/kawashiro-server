import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useEditorKeybindings } from '@/features/pdf-edit/hooks/useEditorKeybindings';
import { usePdfEditStore } from '@/stores/pdf-edit-store';

function Harness() {
    useEditorKeybindings();
    return (
        <>
            <button type="button">本文</button>
            <div role="alertdialog">
                <button type="button">確認の中</button>
            </div>
            <div role="dialog">
                <button type="button">トリミングの中</button>
            </div>
        </>
    );
}

describe('useEditorKeybindings', () => {
    const initialState = usePdfEditStore.getState();
    const undo = vi.fn();
    const redo = vi.fn();

    beforeEach(() => {
        undo.mockClear();
        redo.mockClear();
        usePdfEditStore.setState({ undo, redo });
        render(<Harness />);
    });

    afterEach(() => {
        usePdfEditStore.setState(initialState, true);
    });

    it('本文で Ctrl+Z を押すと元に戻す', () => {
        fireEvent.keyDown(screen.getByRole('button', { name: '本文' }), {
            key: 'z',
            ctrlKey: true,
        });

        expect(undo).toHaveBeenCalledTimes(1);
    });

    it('本文で Ctrl+Y を押すとやり直す', () => {
        fireEvent.keyDown(screen.getByRole('button', { name: '本文' }), {
            key: 'y',
            ctrlKey: true,
        });

        expect(redo).toHaveBeenCalledTimes(1);
    });

    it.each(['確認の中', 'トリミングの中'])(
        'ダイアログ（%s）の中では背後の編集を変えない',
        (name) => {
            const button = screen.getByRole('button', { name });

            fireEvent.keyDown(button, { key: 'z', ctrlKey: true });
            fireEvent.keyDown(button, { key: 'y', ctrlKey: true });

            expect(undo).not.toHaveBeenCalled();
            expect(redo).not.toHaveBeenCalled();
        },
    );
});
