import { RotateCcw } from 'lucide-react';
import { AudioDownload } from '@/components/audio/AudioDownload';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import { ErrorMessage } from '@/components/common/ErrorMessage';
import { PageHeader } from '@/components/common/PageHeader';
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
        <div className="max-w-(--page-max-width)">
            <PageHeader
                eyebrow="Voice"
                title="テキスト読み上げ"
                lead="テキストを入力して音声を生成します"
            />

            <div className="grid items-start gap-5 lg:grid-cols-[1fr_300px]">
                <Card>
                    <CardHeader>
                        <CardTitle>テキスト入力</CardTitle>
                        <CardDescription>
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
                                <Separator />
                                <AudioPlayer src={audioUrl} autoPlay />
                                <AudioDownload
                                    blob={audioBlob}
                                    filename={`tts_output.${format}`}
                                />
                            </div>
                        )}
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader>
                        <div className="flex items-center justify-between">
                            <CardTitle>詳細パラメータ</CardTitle>
                            <Button
                                variant="ghost"
                                size="icon-sm"
                                onClick={resetParams}
                                title="デフォルトに戻す"
                                aria-label="デフォルトに戻す"
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
