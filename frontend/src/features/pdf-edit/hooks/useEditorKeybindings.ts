import { useEffect } from 'react';
import { usePdfEditStore } from '@/stores/pdf-edit-store';

/**
 * PDF編集画面のキーボードショートカット。
 *
 * - Ctrl/Cmd + Z      → Undo
 * - Ctrl/Cmd + Shift + Z または Ctrl/Cmd + Y → Redo
 * - input/textarea/contenteditable にフォーカスがあるときは無視（CropDialogなど）
 */
export function useEditorKeybindings() {
    const undo = usePdfEditStore((s) => s.undo);
    const redo = usePdfEditStore((s) => s.redo);

    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            const target = e.target as HTMLElement | null;
            if (target) {
                const tag = target.tagName?.toLowerCase();
                if (
                    tag === 'input' ||
                    tag === 'textarea' ||
                    target.isContentEditable
                ) {
                    return;
                }
            }
            const mod = e.ctrlKey || e.metaKey;
            if (!mod) return;

            // Shift+Z だと一部ブラウザで e.key が 'Z'（大文字）になる場合があるため
            // toLowerCase() で正規化してから比較する。
            const key = e.key.toLowerCase();
            if (key === 'z' && !e.shiftKey) {
                e.preventDefault();
                undo();
            } else if ((key === 'z' && e.shiftKey) || key === 'y') {
                e.preventDefault();
                redo();
            }
        };
        document.addEventListener('keydown', handler);
        return () => document.removeEventListener('keydown', handler);
    }, [undo, redo]);
}
