import {
    Crop,
    Redo2,
    SplitSquareHorizontal,
    Square,
    SquareCheck,
    Trash2,
    Undo2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { usePdfEditStore } from '@/stores/pdf-edit-store';
import { DownloadButton } from './DownloadButton';

interface EditToolbarProps {
    readonly onCropClick: () => void;
    readonly sourceBytes: ArrayBuffer | null;
    readonly sourceFileName: string | null;
}

export function EditToolbar({
    onCropClick,
    sourceBytes,
    sourceFileName,
}: EditToolbarProps) {
    const pages = usePdfEditStore((s) => s.pages);
    const selection = usePdfEditStore((s) => s.selection);
    const canUndo = usePdfEditStore((s) => s.canUndo());
    const canRedo = usePdfEditStore((s) => s.canRedo());

    const selectAll = usePdfEditStore((s) => s.selectAll);
    const clearSelection = usePdfEditStore((s) => s.clearSelection);
    const deleteSelected = usePdfEditStore((s) => s.deleteSelected);
    const splitSelected = usePdfEditStore((s) => s.splitSelected);
    const undo = usePdfEditStore((s) => s.undo);
    const redo = usePdfEditStore((s) => s.redo);

    const hasSelection = selection.size > 0;

    return (
        <div className="bg-secondary flex flex-wrap items-center gap-2 rounded-lg border p-3">
            {selection.size === pages.length && pages.length > 0 ? (
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={clearSelection}
                    aria-label="すべて選択解除"
                >
                    <Square />
                    解除
                </Button>
            ) : (
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={selectAll}
                    aria-label="すべて選択"
                >
                    <SquareCheck />
                    全選択
                </Button>
            )}

            <Separator orientation="vertical" className="hidden h-6 sm:block" />

            <Button
                variant="ghost"
                size="sm"
                onClick={deleteSelected}
                disabled={!hasSelection}
                aria-label="選択ページを削除"
            >
                <Trash2 />
                削除
            </Button>

            <Button
                variant="ghost"
                size="sm"
                onClick={splitSelected}
                disabled={!hasSelection}
                aria-label="選択ページを左右に分割"
            >
                <SplitSquareHorizontal />
                分割
            </Button>

            <Button
                variant="ghost"
                size="sm"
                onClick={onCropClick}
                disabled={!hasSelection}
                aria-label="選択ページをトリミング"
            >
                <Crop />
                トリミング
            </Button>

            <Separator orientation="vertical" className="hidden h-6 sm:block" />

            <Button
                variant="ghost"
                size="sm"
                onClick={undo}
                disabled={!canUndo}
                aria-label="元に戻す"
            >
                <Undo2 />
                Undo
            </Button>

            <Button
                variant="ghost"
                size="sm"
                onClick={redo}
                disabled={!canRedo}
                aria-label="やり直す"
            >
                <Redo2 />
                Redo
            </Button>

            <div className="text-ink-subtle ml-auto text-xs tabular-nums">
                {selection.size} / {pages.length} ページ選択中
            </div>

            <Separator orientation="vertical" className="hidden h-6 sm:block" />

            <DownloadButton
                sourceBytes={sourceBytes}
                sourceFileName={sourceFileName}
            />
        </div>
    );
}
