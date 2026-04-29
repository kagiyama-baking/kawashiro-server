import { Loader2, Trash2 } from 'lucide-react';
import { useState } from 'react';
import ReactCrop, { type Crop, type PercentCrop } from 'react-image-crop';
import 'react-image-crop/dist/ReactCrop.css';
import { Button } from '@/components/ui/button';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { usePdfEditStore } from '@/stores/pdf-edit-store';
import type { CropRect } from '@/types/pdf-edit';
import { useHighResPreview } from '../hooks/useHighResPreview';

interface CropDialogProps {
    readonly onClose: () => void;
    readonly sourceBytes: ArrayBuffer | null;
}

/**
 * 矩形選択でトリミング範囲を指定するダイアログのゲート。
 *
 * - sourceBytes や 選択ページが無いケースは無視（CropDialog自体を消す）
 * - 内部の {@link CropDialogContent} で実処理を行う。
 *   こうすることで内部コンポーネントは valid な props のみを扱う設計にでき、
 *   フックの条件付き呼び出しを避けられる。
 */
export function CropDialog({ onClose, sourceBytes }: CropDialogProps) {
    const pages = usePdfEditStore((s) => s.pages);
    const selection = usePdfEditStore((s) => s.selection);

    const firstSelected = pages.find((p) => selection.has(p.id));
    if (!sourceBytes || !firstSelected) return null;

    return (
        <CropDialogContent
            onClose={onClose}
            sourceBytes={sourceBytes}
            sourceIndex={firstSelected.sourceIndex}
            initialCrop={firstSelected.crop}
            selectionCount={selection.size}
        />
    );
}

interface CropDialogContentProps {
    readonly onClose: () => void;
    readonly sourceBytes: ArrayBuffer;
    readonly sourceIndex: number;
    readonly initialCrop: CropRect | null;
    readonly selectionCount: number;
}

/**
 * 矩形選択UIの本体。
 *
 * - 元PDFを 2.0 倍で再レンダリングして高解像度プレビューにする
 * - aspect 未指定で自由切り抜き（縦と横で別々の余白幅を指定可能）
 * - 確定すると 0〜1 の相対座標で全選択ページに一括適用
 */
function CropDialogContent({
    onClose,
    sourceBytes,
    sourceIndex,
    initialCrop,
    selectionCount,
}: CropDialogContentProps) {
    const cropSelected = usePdfEditStore((s) => s.cropSelected);
    const clearCropSelected = usePdfEditStore((s) => s.clearCropSelected);
    const preview = useHighResPreview(sourceBytes, sourceIndex);

    const [crop, setCrop] = useState<Crop>(() => {
        if (initialCrop) {
            return {
                unit: '%',
                x: initialCrop.x * 100,
                y: initialCrop.y * 100,
                width: initialCrop.width * 100,
                height: initialCrop.height * 100,
            };
        }
        return { unit: '%', x: 10, y: 10, width: 80, height: 80 };
    });

    const handleApply = () => {
        const percent = ensurePercent(crop);
        if (!percent) {
            onClose();
            return;
        }
        const rect: CropRect = {
            x: percent.x / 100,
            y: percent.y / 100,
            width: percent.width / 100,
            height: percent.height / 100,
        };
        cropSelected(rect);
        onClose();
    };

    const handleClear = () => {
        clearCropSelected();
        onClose();
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="flex h-[95vh] max-h-[95vh] w-[min(95vw,1400px)] max-w-[min(95vw,1400px)] flex-col gap-3">
                <DialogHeader>
                    <DialogTitle>余白トリミング</DialogTitle>
                    <DialogDescription>
                        矩形を調整して、選択中の {selectionCount}{' '}
                        ページに同じ範囲を一括適用します。
                        ページサイズ・座標系は変更せず、表示領域のみが切り詰められます。
                    </DialogDescription>
                </DialogHeader>

                <div className="bg-background/50 flex flex-1 items-center justify-center overflow-auto rounded-lg p-4">
                    {preview.status === 'loading' && (
                        <div className="text-muted-foreground flex items-center gap-2 text-sm">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            高解像度プレビューを生成中…
                        </div>
                    )}
                    {preview.status === 'error' && (
                        <p className="text-destructive text-sm">
                            {preview.errorMessage ??
                                'プレビューの生成に失敗しました'}
                        </p>
                    )}
                    {preview.status === 'ready' && preview.url && (
                        <ReactCrop
                            crop={crop}
                            onChange={(_, percent) => setCrop(percent)}
                            keepSelection
                            ruleOfThirds
                        >
                            <img
                                src={preview.url}
                                alt="トリミングプレビュー"
                                className="max-h-[78vh] max-w-full object-contain"
                            />
                        </ReactCrop>
                    )}
                </div>

                <DialogFooter className="gap-2">
                    <Button
                        variant="ghost"
                        onClick={handleClear}
                        className="mr-auto text-[oklch(0.65_0.25_25)]"
                    >
                        <Trash2 className="mr-1.5 h-4 w-4" />
                        トリミングをクリア
                    </Button>
                    <Button variant="outline" onClick={onClose}>
                        キャンセル
                    </Button>
                    <Button
                        onClick={handleApply}
                        disabled={preview.status !== 'ready'}
                    >
                        適用（{selectionCount} ページ）
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function ensurePercent(crop: Crop): PercentCrop | null {
    if (crop.unit === '%') return crop as PercentCrop;
    // px のときはコンテナサイズが分からないと変換できないため、null を返してキャンセル相当にする
    // （react-image-crop の onChange は percent も同時に返すため、そちらをstateに保存することで通常はここに来ない）
    return null;
}
