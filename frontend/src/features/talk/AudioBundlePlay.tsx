import { Loader2, Play, Square } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
    countPlayableAudios,
    isAllWav,
    loadSessionAudios,
} from '@/lib/audio/bundleLoader';
import { concatWavBlobs } from '@/lib/audio/concat';
import { SILENT_WAV_DATA_URL } from '@/lib/audio/silent';
import type { ChatSessionMessage } from '@/types/talk';

interface AudioBundlePlayProps {
    readonly sessionId: string;
    readonly messages: readonly ChatSessionMessage[];
    readonly disabled?: boolean;
}

function formatTime(seconds: number): string {
    if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${String(s).padStart(2, '0')}`;
}

export function AudioBundlePlay({
    sessionId,
    messages,
    disabled = false,
}: AudioBundlePlayProps) {
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const objectUrlRef = useRef<string | null>(null);

    const [isPreparing, setIsPreparing] = useState(false);
    const [isPlaying, setIsPlaying] = useState(false);
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);

    const audioCount = countPlayableAudios(messages);

    const stop = () => {
        const audio = audioRef.current;
        if (audio) {
            audio.pause();
            audio.removeAttribute('src');
            audio.load();
            audioRef.current = null;
        }
        if (objectUrlRef.current) {
            URL.revokeObjectURL(objectUrlRef.current);
            objectUrlRef.current = null;
        }
        setIsPlaying(false);
        setCurrentTime(0);
        setDuration(0);
    };

    useEffect(() => {
        return () => {
            stop();
        };
    }, []);

    // セッション切替時 / メッセージ件数変化時は停止
    useEffect(() => {
        stop();
    }, [sessionId]);

    const handlePlay = async () => {
        if (audioCount === 0 || isPreparing) return;

        // iOS Safari の autoplay policy 対策: ユーザー操作と同期して
        // 先に無音 WAV を play() し audio 要素をアンロックしておく。
        // 結合処理は時間がかかるため、await を挟むと autoplay 起点が切れる。
        // ended/timeupdate のリスナーは「unlock 用 silent」では発火させたくない
        // ので、本データ差し替え後に attach する。
        const audio = new Audio(SILENT_WAV_DATA_URL);
        audioRef.current = audio;

        try {
            await audio.play();
            audio.pause(); // unlock 完了直後に止める（silent ended → stop の暴発防止）
        } catch (err) {
            console.warn('音声アンロックに失敗:', err);
            toast.error('音声再生が許可されませんでした');
            stop();
            return;
        }

        setIsPreparing(true);
        try {
            const audios = await loadSessionAudios(sessionId, messages);
            if (audios.length === 0) {
                toast.error('再生可能な音声がありません');
                stop();
                return;
            }
            if (!isAllWav(audios)) {
                toast.error('一括再生は WAV のみ対応しています');
                stop();
                return;
            }
            const merged = await concatWavBlobs(
                audios.map((a) => a.blob),
                1,
            );
            const url = URL.createObjectURL(merged);
            objectUrlRef.current = url;

            // 本データ差し替え後にリスナーを attach
            audio.src = url;
            audio.addEventListener('loadedmetadata', () => {
                setDuration(audio.duration);
            });
            audio.addEventListener('timeupdate', () => {
                setCurrentTime(audio.currentTime);
            });
            audio.addEventListener('ended', () => {
                stop();
            });
            audio.load();
            await audio.play();
            setIsPlaying(true);
        } catch (err) {
            console.warn('音声の一括再生に失敗:', err);
            toast.error('音声の一括再生に失敗しました');
            stop();
        } finally {
            setIsPreparing(false);
        }
    };

    const handleStop = () => {
        stop();
    };

    if (isPlaying) {
        return (
            <Button
                type="button"
                variant="destructive"
                size="sm"
                onClick={handleStop}
            >
                <Square className="mr-1.5 h-3.5 w-3.5" fill="currentColor" />
                停止 {formatTime(currentTime)} / {formatTime(duration)}
            </Button>
        );
    }

    return (
        <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handlePlay}
            disabled={disabled || isPreparing || audioCount === 0}
        >
            {isPreparing ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : (
                <Play className="mr-1.5 h-3.5 w-3.5" fill="currentColor" />
            )}
            一括再生 ({audioCount})
        </Button>
    );
}
