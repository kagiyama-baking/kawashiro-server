import { Upload } from 'lucide-react';
import { type ChangeEvent, useRef } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface PdfFileUploaderProps {
    readonly onFileSelected: (file: File) => void;
    readonly disabled?: boolean;
}

// クライアント完結のため大きすぎるPDFはブラウザがハングする可能性あり。
// 警告のみで処理は試みる。
const SOFT_LIMIT_BYTES = 200 * 1024 * 1024; // 200MB

export function PdfFileUploader({
    onFileSelected,
    disabled,
}: PdfFileUploaderProps) {
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;
        if (file.size > SOFT_LIMIT_BYTES) {
            const mb = Math.round(file.size / (1024 * 1024));
            const proceed = window.confirm(
                `ファイルサイズが${mb}MBあります（推奨: 200MB以下）。\n` +
                    `処理は試みますが、ブラウザが重くなる可能性があります。続行しますか？`,
            );
            if (!proceed) {
                e.target.value = '';
                return;
            }
        }
        onFileSelected(file);
    };

    const handleClick = () => {
        fileInputRef.current?.click();
    };

    return (
        <div className="space-y-2">
            <Label htmlFor="pdf-file" className="text-[13px] font-medium">
                PDFファイル
            </Label>
            <div className="flex items-center gap-3">
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
                    className="transition-all duration-200 hover:shadow-[0_0_12px_oklch(0.75_0.20_155/0.15)]"
                >
                    <Upload className="mr-2 h-4 w-4" />
                    PDFを選択
                </Button>
                <p className="text-muted-foreground text-[11px]">
                    クライアント側で処理（ファイルはサーバーに送信されません）
                </p>
            </div>
        </div>
    );
}
