import { AudioDownload } from '@/components/audio/AudioDownload';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import { ErrorMessage } from '@/components/common/ErrorMessage';
import { TerminalText } from '@/components/common/TerminalText';
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { GenerateForm } from './GenerateForm';
import { useGenerate } from './useGenerate';

export function GeneratePage() {
    const {
        configs,
        selectedConfig,
        setSelectedConfig,
        result,
        isLoading,
        error,
        handleGenerate,
    } = useGenerate();

    return (
        <div className="mx-auto max-w-4xl space-y-6">
            <div className="animate-slide-up">
                <h1 className="font-heading text-foreground text-2xl font-bold tracking-tight">
                    会話生成読み上げ
                </h1>
                <TerminalText text="talk --generate" />
            </div>

            <Card className="animate-slide-up neon-border">
                <CardHeader>
                    <CardTitle className="font-heading font-semibold">
                        プロンプト設定
                    </CardTitle>
                    <CardDescription className="text-[13px]">
                        プリセットを選択し、ユーザープロンプトを入力してください
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <GenerateForm
                        configs={configs}
                        selectedConfig={selectedConfig}
                        onConfigChange={setSelectedConfig}
                        onSubmit={handleGenerate}
                        isLoading={isLoading}
                    />

                    <ErrorMessage message={error} />

                    {result && (
                        <div className="animate-slide-up mt-5 space-y-3">
                            <Separator className="opacity-30" />
                            {result.text && (
                                <div className="glass rounded-xl p-5">
                                    <p className="text-foreground font-mono text-[13px] leading-relaxed whitespace-pre-wrap">
                                        {result.text}
                                    </p>
                                </div>
                            )}
                            {result.audioUrl && (
                                <>
                                    <AudioPlayer
                                        src={result.audioUrl}
                                        autoPlay
                                    />
                                    <AudioDownload
                                        blob={result.audioBlob}
                                        filename="generated.wav"
                                    />
                                </>
                            )}
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
