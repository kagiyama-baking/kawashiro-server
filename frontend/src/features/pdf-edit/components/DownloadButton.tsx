import { Download } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { LoadingButton } from '@/components/common/LoadingButton';
import { makeEditedFileName } from '@/lib/pdf/file-name';
import { EmptyOutputError, applyEditsAndExport } from '@/lib/pdf/pdf-mutations';
import { usePdfEditStore } from '@/stores/pdf-edit-store';

interface DownloadButtonProps {
    readonly sourceBytes: ArrayBuffer | null;
    readonly sourceFileName: string | null;
}

export function DownloadButton({
    sourceBytes,
    sourceFileName,
}: DownloadButtonProps) {
    const pages = usePdfEditStore((s) => s.pages);
    const [isExporting, setIsExporting] = useState(false);

    const disabled = !sourceBytes || pages.length === 0 || isExporting;

    const handleDownload = async () => {
        if (!sourceBytes) return;
        setIsExporting(true);
        let url: string | null = null;
        try {
            const bytes = await applyEditsAndExport(sourceBytes, pages);
            // Uint8Array<ArrayBufferLike> をそのまま Blob に渡すと
            // TS 5.7+ の SharedArrayBuffer 互換型エラーになるため、
            // ArrayBuffer に切り出してから渡す。
            const buffer = bytes.buffer.slice(
                bytes.byteOffset,
                bytes.byteOffset + bytes.byteLength,
            ) as ArrayBuffer;
            const blob = new Blob([buffer], { type: 'application/pdf' });
            url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = makeEditedFileName(sourceFileName);
            document.body.appendChild(a);
            a.click();
            a.remove();
            toast.success('編集後のPDFをダウンロードしました');
        } catch (e) {
            if (e instanceof EmptyOutputError) {
                toast.error('出力するページがありません');
            } else if (e instanceof Error) {
                toast.error(`PDFの出力に失敗しました: ${e.message}`);
            } else {
                toast.error('PDFの出力に失敗しました');
            }
        } finally {
            // a.click() 直後の revoke は Firefox 等で稀にダウンロード開始前に
            // URL が無効化されるレースがあるため、次フレームに遅延する。
            if (url) {
                const u = url;
                setTimeout(() => URL.revokeObjectURL(u), 0);
            }
            setIsExporting(false);
        }
    };

    return (
        <LoadingButton
            type="button"
            onClick={handleDownload}
            disabled={disabled}
            isLoading={isExporting}
            loadingText="出力中…"
            className="transition-all duration-200 hover:shadow-[0_0_12px_oklch(0.75_0.20_155/0.15)]"
        >
            <Download className="mr-1.5 h-4 w-4" />
            ダウンロード
        </LoadingButton>
    );
}
