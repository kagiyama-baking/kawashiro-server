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
        <Button variant="outline" size="sm" onClick={handleDownload}>
            <Download className="mr-2 h-4 w-4" />
            ダウンロード
        </Button>
    );
}
