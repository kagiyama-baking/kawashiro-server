import { Upload } from 'lucide-react';
import { type ChangeEvent, useRef, useState } from 'react';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface PdfFileUploaderProps {
    readonly onFileSelected: (file: File) => void;
    readonly disabled?: boolean;
}

interface OversizedFile {
    readonly file: File;
    readonly isConfirming: boolean;
}

// クライアント完結のため大きすぎるPDFはブラウザがハングする可能性あり。
// 警告のみで処理は試みる。
const SOFT_LIMIT_BYTES = 200 * 1024 * 1024; // 200MB

export function PdfFileUploader({
    onFileSelected,
    disabled,
}: PdfFileUploaderProps) {
    const fileInputRef = useRef<HTMLInputElement>(null);
    // 閉じるアニメーションの間も文面が変わらないよう、確認を終えてもファイルは保持する
    const [oversized, setOversized] = useState<OversizedFile | null>(null);

    const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        if (file.size > SOFT_LIMIT_BYTES) {
            setOversized({ file, isConfirming: true });
            return;
        }
        onFileSelected(file);
    };

    const handleProceed = () => {
        if (!oversized) return;
        setOversized({ ...oversized, isConfirming: false });
        onFileSelected(oversized.file);
    };

    const handleAbort = () => {
        if (!oversized) return;
        setOversized({ ...oversized, isConfirming: false });
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    const handleClick = () => {
        fileInputRef.current?.click();
    };

    const oversizedMb = oversized
        ? Math.round(oversized.file.size / (1024 * 1024))
        : 0;

    return (
        <div className="space-y-2">
            <Label htmlFor="pdf-file">PDFファイル</Label>
            <div className="flex flex-wrap items-center gap-3">
                <Input
                    id="pdf-file"
                    ref={fileInputRef}
                    type="file"
                    accept="application/pdf,.pdf"
                    onChange={handleChange}
                    disabled={disabled}
                    className="hidden"
                />
                <Button
                    type="button"
                    variant="outline"
                    onClick={handleClick}
                    disabled={disabled}
                >
                    <Upload />
                    PDFを選択
                </Button>
                <p className="text-muted-foreground text-xs">
                    クライアント側で処理（ファイルはサーバーに送信されません）
                </p>
            </div>

            <ConfirmDialog
                open={oversized?.isConfirming ?? false}
                title="大きなファイルです"
                confirmLabel="続行"
                onConfirm={handleProceed}
                onCancel={handleAbort}
            >
                ファイルサイズが{oversizedMb}MBあります（推奨:
                200MB以下）。処理は試みますが、ブラウザが重くなる可能性があります。続行しますか？
            </ConfirmDialog>
        </div>
    );
}
