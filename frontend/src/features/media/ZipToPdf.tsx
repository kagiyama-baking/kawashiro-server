import { type FormEvent, useRef } from 'react';
import { Button } from '@/components/ui/button';
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
        <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
                <Label htmlFor="zip-file">ZIPファイル</Label>
                <Input
                    id="zip-file"
                    ref={fileInputRef}
                    type="file"
                    accept=".zip"
                    required
                />
                <p className="text-xs text-muted-foreground">
                    画像を含むZIPファイルをアップロードしてください（最大1GB、最大1000ファイル）
                </p>
            </div>

            <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? '変換中...' : 'PDFに変換'}
            </Button>
        </form>
    );
}
