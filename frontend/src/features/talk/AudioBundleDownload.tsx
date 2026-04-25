import { Download } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { concatWavBlobs, formatTimestampForFilename } from '@/lib/audio/concat';
import type { ChatMessageResult } from '@/types/talk';

interface AudioBundleDownloadProps {
    readonly messages: ChatMessageResult[];
}

interface AudioMessage {
    readonly audioBlob: Blob;
    readonly audioFormat: string;
}

function pickAudioMessages(messages: ChatMessageResult[]): AudioMessage[] {
    const result: AudioMessage[] = [];
    for (const m of messages) {
        if (m.audioBlob !== null && m.audioFormat !== null) {
            result.push({ audioBlob: m.audioBlob, audioFormat: m.audioFormat });
        }
    }
    return result;
}

export function AudioBundleDownload({ messages }: AudioBundleDownloadProps) {
    const [isProcessing, setIsProcessing] = useState(false);

    const audioMessages = pickAudioMessages(messages);
    if (audioMessages.length === 0) return null;

    const handleDownload = async () => {
        setIsProcessing(true);
        try {
            const blobs = audioMessages.map((m) => m.audioBlob);
            const formats = new Set(audioMessages.map((m) => m.audioFormat));
            const ext = audioMessages[0].audioFormat;

            const combined =
                formats.size === 1 && ext === 'wav'
                    ? await concatWavBlobs(blobs)
                    : new Blob(blobs, { type: blobs[0].type });

            const filename = `chat-${formatTimestampForFilename(new Date())}.${ext}`;
            const url = URL.createObjectURL(combined);
            try {
                const a = document.createElement('a');
                a.href = url;
                a.download = filename;
                a.click();
            } finally {
                URL.revokeObjectURL(url);
            }
        } catch (err) {
            console.error('音声結合に失敗:', err);
            toast.error('音声の結合に失敗しました');
        } finally {
            setIsProcessing(false);
        }
    };

    return (
        <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleDownload}
            disabled={isProcessing}
            className="shrink-0"
        >
            <Download className="mr-1.5 h-4 w-4" />
            音声を一括ダウンロード ({audioMessages.length})
        </Button>
    );
}
