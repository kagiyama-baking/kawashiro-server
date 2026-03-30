import { type FormEvent, useRef } from 'react';
import { LoadingButton } from '@/components/common/LoadingButton';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface ZipToPdfProps {
    readonly onSubmit: (file: File) => void;
    readonly isLoading: boolean;
}

export function ZipToPdf({ onSubmit, isLoading }: ZipToPdfProps) {
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleSubmit = (e: FormEvent) => {
        e.preventDefault();
        const file = fileInputRef.current?.files?.[0];
        if (!file) return;
        onSubmit(file);
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-3.5">
            <div className="space-y-2">
                <Label htmlFor="zip-file" className="text-[13px] font-medium">
                    ZIPファイル
                </Label>
                <Input
                    id="zip-file"
                    ref={fileInputRef}
                    type="file"
                    accept=".zip"
                    required
                />
                <p className="text-muted-foreground text-[11px]">
                    画像を含むZIPファイルをアップロードしてください（最大1GB、最大1000ファイル）
                </p>
            </div>

            <LoadingButton
                type="submit"
                className="mt-1 w-full font-medium"
                isLoading={isLoading}
                loadingText="変換中..."
            >
                PDFに変換
            </LoadingButton>
        </form>
    );
}
