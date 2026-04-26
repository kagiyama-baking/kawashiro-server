import { Loader2, Play, Square } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
    countPlayableAudios,
    isAllWav,
    loadSessionAudios,
} from '@/lib/audio/bundleLoader';
import { concatWavBlobs } from '@/lib/audio/concat';
import type { ChatSessionMessage } from '@/types/talk';

interface AudioBundlePlayProps {
    readonly sessionId: string;
    readonly messages: readonly ChatSessionMessage[];
    readonly disabled?: boolean;
}

// idle    : 初期 / 完全停止
// preparing: 音声を fetch + 結合中
// ready   : 結合完了、ユーザー操作起点での再生待ち（iOS autoplay 対策）
// playing : 再生中
type Phase = 'idle' | 'preparing' | 'ready' | 'playing';

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

    const [phase, setPhase] = useState<Phase>('idle');
    const [currentTime, setCurrentTime] = useState(0);
    const [duration, setDuration] = useState(0);

    const audioCount = countPlayableAudios(messages);

    // setState 関数 (setCurrentTime / setDuration / setPhase) は React により
    // 安定参照が保証されるため、useCallback の依存配列は空でよい。
    const stop = useCallback(() => {
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
        setCurrentTime(0);
        setDuration(0);
        setPhase('idle');
    }, []);

    // unmount およびセッション切替時に進行中の再生を停止
    useEffect(() => {
        return () => stop();
    }, [stop]);

    useEffect(() => {
        return () => stop();
    }, [sessionId, stop]);

    const prepare = async () => {
        if (audioCount === 0 || phase !== 'idle') return;
        setPhase('preparing');
        try {
            const audios = await loadSessionAudios(sessionId, messages);
            if (audios.length === 0) {
                toast.error('再生可能な音声がありません');
                setPhase('idle');
                return;
            }
            if (!isAllWav(audios)) {
                toast.error('一括再生は WAV のみ対応しています');
                setPhase('idle');
                return;
            }
            const merged = await concatWavBlobs(
                audios.map((a) => a.blob),
                1,
            );
            const url = URL.createObjectURL(merged);
            objectUrlRef.current = url;

            const audio = new Audio(url);
            audioRef.current = audio;
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

            // PC ブラウザ等 autoplay policy が緩い環境ではここで再生開始。
            // iOS Safari は await を挟むと拒否されるので catch して ready 表示
            // へフォールバックし、ユーザーの直接タップで play() を呼ぶ。
            try {
                await audio.play();
                setPhase('playing');
            } catch (err) {
                console.warn(
                    '自動再生不可、ユーザー操作待ちへフォールバック:',
                    err,
                );
                setPhase('ready');
            }
        } catch (err) {
            console.warn('音声の準備に失敗:', err);
            toast.error('音声の準備に失敗しました');
            stop();
        }
    };

    const playPrepared = async () => {
        const audio = audioRef.current;
        if (!audio) return;
        try {
            await audio.play();
            setPhase('playing');
        } catch (err) {
            console.warn('再生開始に失敗:', err);
            toast.error('再生が許可されませんでした');
        }
    };

    if (phase === 'playing') {
        return (
            <Button
                type="button"
                variant="destructive"
                size="sm"
                onClick={stop}
            >
                <Square className="mr-1.5 h-3.5 w-3.5" fill="currentColor" />
                停止 {formatTime(currentTime)} / {formatTime(duration)}
            </Button>
        );
    }

    if (phase === 'ready') {
        return (
            <Button
                type="button"
                size="sm"
                onClick={playPrepared}
                disabled={disabled}
            >
                <Play className="mr-1.5 h-3.5 w-3.5" fill="currentColor" />
                再生開始 ({formatTime(duration)})
            </Button>
        );
    }

    if (phase === 'preparing') {
        return (
            <Button type="button" variant="outline" size="sm" disabled>
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                準備中…
            </Button>
        );
    }

    return (
        <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={prepare}
            disabled={disabled || audioCount === 0}
        >
            <Play className="mr-1.5 h-3.5 w-3.5" fill="currentColor" />
            一括再生 ({audioCount})
        </Button>
    );
}
