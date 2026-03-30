import { RotateCcw } from 'lucide-react';
import { AudioDownload } from '@/components/audio/AudioDownload';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import { ErrorMessage } from '@/components/common/ErrorMessage';
import { Button } from '@/components/ui/button';
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { useTtsStore } from '@/stores/tts-store';
import { TtsForm } from './TtsForm';
import { TtsParamSliders } from './TtsParamSliders';
import { useTts } from './useTts';

export function TtsPage() {
    const {
        models,
        styles,
        selectedModel,
        setSelectedModel,
        audioUrl,
        audioBlob,
        isLoading,
        error,
        handleSynthesize,
    } = useTts();

    const resetParams = useTtsStore((s) => s.resetParams);
    const format = useTtsStore((s) => s.params.format);

    return (
        <div className="mx-auto max-w-4xl space-y-6">
            <div className="animate-slide-up">
                <h1 className="font-heading text-foreground text-2xl font-bold tracking-tight">
                    テキスト読み上げ
                </h1>
                <p className="text-muted-foreground mt-1 font-mono text-xs">
                    // text-to-speech synthesis
                </p>
            </div>

            <div className="grid gap-5 lg:grid-cols-[1fr_300px]">
                <Card className="animate-slide-up neon-border">
                    <CardHeader>
                        <CardTitle className="font-heading font-semibold">
                            テキスト入力
                        </CardTitle>
                        <CardDescription className="text-[13px]">
                            読み上げたいテキストとパラメータを設定してください
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <TtsForm
                            models={models}
                            styles={styles}
                            selectedModel={selectedModel}
                            onModelChange={setSelectedModel}
                            onSubmit={handleSynthesize}
                            isLoading={isLoading}
                        />

                        <ErrorMessage message={error} />

                        {audioUrl && (
                            <div className="animate-slide-up mt-5 space-y-3">
                                <Separator className="opacity-30" />
                                <AudioPlayer src={audioUrl} autoPlay />
                                <AudioDownload
                                    blob={audioBlob}
                                    filename={`tts_output.${format}`}
                                />
                            </div>
                        )}
                    </CardContent>
                </Card>

                <Card
                    className="animate-slide-up neon-border"
                    style={{ animationDelay: '100ms' }}
                >
                    <CardHeader>
                        <div className="flex items-center justify-between">
                            <CardTitle className="font-heading text-sm font-semibold">
                                詳細パラメータ
                            </CardTitle>
                            <Button
                                variant="ghost"
                                size="icon"
                                onClick={resetParams}
                                title="デフォルトに戻す"
                                aria-label="デフォルトに戻す"
                                className="hover:text-[oklch(0.82_0.18_192)]"
                            >
                                <RotateCcw className="h-4 w-4" />
                            </Button>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <TtsParamSliders />
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
