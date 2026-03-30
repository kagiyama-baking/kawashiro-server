import { Download } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface AudioDownloadProps {
    readonly blob: Blob | null;
    readonly filename?: string;
}

export function AudioDownload({
    blob,
    filename = 'audio.wav',
}: AudioDownloadProps) {
    if (!blob) return null;

    const handleDownload = () => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    };

    return (
        <Button
            variant="outline"
            size="sm"
            className="transition-all duration-200 hover:shadow-[0_0_12px_oklch(0.82_0.18_192/0.15)]"
            onClick={handleDownload}
        >
            <Download className="mr-1.5 h-4 w-4" />
            ダウンロード
        </Button>
    );
}
