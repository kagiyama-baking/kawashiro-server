import { type FormEvent, useRef, useState } from 'react';
import { LoadingButton } from '@/components/common/LoadingButton';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import type { OutputFormat } from '@/types/media';

interface ImageConverterProps {
    readonly onSubmit: (
        file: File,
        outputFormat: OutputFormat,
        quality: number,
    ) => void;
    readonly isLoading: boolean;
}

export function ImageConverter({ onSubmit, isLoading }: ImageConverterProps) {
    const [outputFormat, setOutputFormat] = useState<OutputFormat>('png');
    const [quality, setQuality] = useState(85);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleSubmit = (e: FormEvent) => {
        e.preventDefault();
        const file = fileInputRef.current?.files?.[0];
        if (!file) return;
        onSubmit(file, outputFormat, quality);
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
                <Label htmlFor="image-file">画像ファイル</Label>
                <Input
                    id="image-file"
                    ref={fileInputRef}
                    type="file"
                    accept=".jpg,.jpeg,.png,.webp,.tiff,.heif,.heic,.psd,.dng"
                    required
                />
                <p className="text-xs text-muted-foreground">
                    対応形式: JPG, PNG, WEBP, TIFF, HEIF, HEIC, PSD,
                    DNG（最大50MB）
                </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                    <Label>出力形式</Label>
                    <Select
                        value={outputFormat}
                        onValueChange={(v) =>
                            setOutputFormat(v as OutputFormat)
                        }
                    >
                        <SelectTrigger>
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="jpg">JPG</SelectItem>
                            <SelectItem value="png">PNG</SelectItem>
                            <SelectItem value="webp">WEBP</SelectItem>
                            <SelectItem value="tiff">TIFF</SelectItem>
                        </SelectContent>
                    </Select>
                </div>

                {outputFormat === 'jpg' && (
                    <div className="space-y-2">
                        <div className="flex items-center justify-between">
                            <Label>品質</Label>
                            <span className="text-sm text-muted-foreground">
                                {quality}
                            </span>
                        </div>
                        <Slider
                            value={[quality]}
                            min={1}
                            max={100}
                            step={1}
                            onValueChange={([v]) => setQuality(v)}
                        />
                    </div>
                )}
            </div>

            <LoadingButton
                type="submit"
                className="w-full"
                isLoading={isLoading}
                loadingText="変換中..."
            >
                変換
            </LoadingButton>
        </form>
    );
}
