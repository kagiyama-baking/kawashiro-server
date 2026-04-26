import { Download } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { concatWavBlobs, formatTimestampForFilename } from '@/lib/audio/concat';
import {
    countPlayableAudios,
    isAllWav,
    loadSessionAudios,
} from '@/lib/audio/bundleLoader';
import type { ChatSessionMessage } from '@/types/talk';

interface AudioBundleDownloadProps {
    readonly sessionId: string;
    readonly messages: readonly ChatSessionMessage[];
    readonly disabled?: boolean;
}

export function AudioBundleDownload({
    sessionId,
    messages,
    disabled = false,
}: AudioBundleDownloadProps) {
    const [isProcessing, setIsProcessing] = useState(false);

    const audioCount = countPlayableAudios(messages);
    const isDisabled = disabled || isProcessing || audioCount === 0;

    const handleClick = async () => {
        setIsProcessing(true);
        try {
            const audios = await loadSessionAudios(sessionId, messages);
            if (audios.length === 0) return;

            const allWav = isAllWav(audios);
            const ext = allWav ? 'wav' : audios[0].format || 'bin';
            const merged = allWav
                ? await concatWavBlobs(
                      audios.map((a) => a.blob),
                      1,
                  )
                : new Blob(audios.map((a) => a.blob));

            const url = URL.createObjectURL(merged);
            const a = document.createElement('a');
            a.href = url;
            a.download = `chat-${formatTimestampForFilename(new Date())}.${ext}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch {
            toast.error('音声の一括ダウンロードに失敗しました');
        } finally {
            setIsProcessing(false);
        }
    };

    return (
        <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleClick}
            disabled={isDisabled}
        >
            <Download className="mr-1.5 h-4 w-4" />
            一括 DL ({audioCount})
        </Button>
    );
}
