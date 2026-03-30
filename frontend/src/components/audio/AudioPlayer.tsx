import { Pause, Play } from 'lucide-react';
import { useCallback, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';

interface AudioPlayerProps {
    readonly src: string | null;
    readonly autoPlay?: boolean;
}

function AudioPlayerInner({
    src,
    autoPlay = false,
}: {
    readonly src: string;
    readonly autoPlay: boolean;
}) {
    const audioRef = useRef<HTMLAudioElement | null>(null);
    const [isPlaying, setIsPlaying] = useState(false);
    const [progress, setProgress] = useState(0);
    const [duration, setDuration] = useState(0);

    const togglePlay = useCallback(() => {
        const audio = audioRef.current;
        if (!audio) return;

        if (isPlaying) {
            audio.pause();
        } else {
            audio.play();
        }
    }, [isPlaying]);

    const handleSeek = useCallback((value: number[]) => {
        const audio = audioRef.current;
        if (!audio) return;
        audio.currentTime = value[0];
        setProgress(value[0]);
    }, []);

    const formatTime = (seconds: number) => {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    };

    return (
        <div className="glass neon-border flex items-center gap-3 rounded-xl p-3.5">
            <audio
                ref={audioRef}
                src={src}
                autoPlay={autoPlay}
                onTimeUpdate={() => {
                    if (audioRef.current)
                        setProgress(audioRef.current.currentTime);
                }}
                onLoadedMetadata={() => {
                    if (audioRef.current)
                        setDuration(audioRef.current.duration);
                }}
                onEnded={() => {
                    setIsPlaying(false);
                    setProgress(0);
                }}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
            />
            <Button
                variant="ghost"
                size="icon"
                onClick={togglePlay}
                className="hover:bg-[oklch(0.82_0.18_192/0.1)] hover:text-[oklch(0.82_0.18_192)]"
                aria-label={isPlaying ? '一時停止' : '再生'}
            >
                {isPlaying ? (
                    <Pause className="h-5 w-5" />
                ) : (
                    <Play className="h-5 w-5" />
                )}
            </Button>
            <div className="flex flex-1 items-center gap-2">
                <span className="text-muted-foreground w-10 font-mono text-[11px] tabular-nums">
                    {formatTime(progress)}
                </span>
                <Slider
                    value={[progress]}
                    max={duration || 1}
                    step={0.1}
                    onValueChange={handleSeek}
                    className="flex-1"
                />
                <span className="text-muted-foreground w-10 font-mono text-[11px] tabular-nums">
                    {formatTime(duration)}
                </span>
            </div>
        </div>
    );
}

export function AudioPlayer({ src, autoPlay = false }: AudioPlayerProps) {
    if (!src) return null;
    // key={src}で src 変更時にコンポーネントをリマウントし、ステートをリセット
    return <AudioPlayerInner key={src} src={src} autoPlay={autoPlay} />;
}
