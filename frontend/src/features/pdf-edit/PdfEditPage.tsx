import { Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { ErrorMessage } from '@/components/common/ErrorMessage';
import { TerminalText } from '@/components/common/TerminalText';
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import '@/lib/pdf/pdf-worker';
import { usePdfEditStore } from '@/stores/pdf-edit-store';
import { CropDialog } from './components/CropDialog';
import { EditToolbar } from './components/EditToolbar';
import { PageThumbnailGrid } from './components/PageThumbnailGrid';
import { PdfFileUploader } from './components/PdfFileUploader';
import { useEditorKeybindings } from './hooks/useEditorKeybindings';
import { usePdfDocument } from './hooks/usePdfDocument';

export function PdfEditPage() {
    const {
        sourceBytes,
        sourceFileName,
        sourcePages,
        isLoading,
        progress,
        error,
        loadFile,
    } = usePdfDocument();
    const initFromSource = usePdfEditStore((s) => s.initFromSource);
    const reset = usePdfEditStore((s) => s.reset);
    const editorPages = usePdfEditStore((s) => s.pages);
    const [cropDialogOpen, setCropDialogOpen] = useState(false);

    useEditorKeybindings();

    // sourcePages が更新されたら編集ストアを初期化
    useEffect(() => {
        if (sourcePages.length > 0) {
            initFromSource(sourcePages);
        } else {
            reset();
        }
    }, [sourcePages, initFromSource, reset]);

    // アンマウント時にストアもクリア
    useEffect(() => {
        return () => {
            reset();
        };
    }, [reset]);

    return (
        <div className="mx-auto max-w-6xl space-y-6">
            <div className="animate-slide-up">
                <h1 className="font-heading text-foreground text-2xl font-bold tracking-tight">
                    PDF編集
                </h1>
                <TerminalText text="pdf-edit --pages" />
            </div>

            <Card className="animate-slide-up neon-border">
                <CardHeader>
                    <CardTitle className="font-heading font-semibold">
                        ページ編集
                    </CardTitle>
                    <CardDescription className="text-[13px]">
                        並び替え・削除・分割・余白トリミングを1画面で行います。クリック=単一選択
                        / Shift+クリック=範囲選択 /
                        Ctrl(Cmd)+クリック=トグル選択。
                    </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                    <PdfFileUploader
                        onFileSelected={loadFile}
                        disabled={isLoading}
                    />

                    {isLoading && (
                        <div className="text-muted-foreground flex items-center gap-2 text-[13px]">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            {progress
                                ? `サムネイル生成中… ${progress.current} / ${progress.total}`
                                : 'PDFを読み込み中…'}
                        </div>
                    )}

                    <ErrorMessage message={error} />

                    {editorPages.length > 0 && (
                        <>
                            <Separator className="opacity-30" />
                            <EditToolbar
                                onCropClick={() => setCropDialogOpen(true)}
                                sourceBytes={sourceBytes}
                                sourceFileName={sourceFileName}
                            />
                            <PageThumbnailGrid sources={sourcePages} />
                            {cropDialogOpen && (
                                <CropDialog
                                    onClose={() => setCropDialogOpen(false)}
                                    sourceBytes={sourceBytes}
                                />
                            )}
                        </>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
