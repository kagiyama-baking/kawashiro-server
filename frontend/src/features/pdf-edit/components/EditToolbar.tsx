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
        <div className="glass flex flex-wrap items-center gap-2 rounded-xl p-3">
            {selection.size === pages.length && pages.length > 0 ? (
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={clearSelection}
                    aria-label="すべて選択解除"
                >
                    <Square className="mr-1.5 h-4 w-4" />
                    解除
                </Button>
            ) : (
                <Button
                    variant="ghost"
                    size="sm"
                    onClick={selectAll}
                    aria-label="すべて選択"
                >
                    <SquareCheck className="mr-1.5 h-4 w-4" />
                    全選択
                </Button>
            )}

            <Separator orientation="vertical" className="h-6 opacity-30" />

            <Button
                variant="ghost"
                size="sm"
                onClick={deleteSelected}
                disabled={!hasSelection}
                aria-label="選択ページを削除"
            >
                <Trash2 className="mr-1.5 h-4 w-4" />
                削除
            </Button>

            <Button
                variant="ghost"
                size="sm"
                onClick={splitSelected}
                disabled={!hasSelection}
                aria-label="選択ページを左右に分割"
            >
                <SplitSquareHorizontal className="mr-1.5 h-4 w-4" />
                分割
            </Button>

            <Button
                variant="ghost"
                size="sm"
                onClick={onCropClick}
                disabled={!hasSelection}
                aria-label="選択ページをトリミング"
            >
                <Crop className="mr-1.5 h-4 w-4" />
                トリミング
            </Button>

            <Separator orientation="vertical" className="h-6 opacity-30" />

            <Button
                variant="ghost"
                size="sm"
                onClick={undo}
                disabled={!canUndo}
                aria-label="元に戻す"
            >
                <Undo2 className="mr-1.5 h-4 w-4" />
                Undo
            </Button>

            <Button
                variant="ghost"
                size="sm"
                onClick={redo}
                disabled={!canRedo}
                aria-label="やり直す"
            >
                <Redo2 className="mr-1.5 h-4 w-4" />
                Redo
            </Button>

            <div className="text-muted-foreground ml-auto font-mono text-[12px] tabular-nums">
                {selection.size} / {pages.length} ページ選択中
            </div>

            <Separator orientation="vertical" className="h-6 opacity-30" />

            <DownloadButton
                sourceBytes={sourceBytes}
                sourceFileName={sourceFileName}
            />
        </div>
    );
}
