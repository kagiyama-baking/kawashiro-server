import { AudioDownload } from '@/components/audio/AudioDownload';
import { AudioPlayer } from '@/components/audio/AudioPlayer';
import { ErrorMessage } from '@/components/common/ErrorMessage';
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
            <div>
                <h1 className="text-foreground text-2xl font-bold">
                    会話生成読み上げ
                </h1>
                <p className="text-muted-foreground text-sm">
                    事前登録済みの設定に基づき会話テキストを生成し、音声で再生します
                </p>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle className="font-sans">プロンプト設定</CardTitle>
                    <CardDescription>
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
                        <div className="mt-4 space-y-3">
                            <Separator />
                            {result.text && (
                                <div className="bg-muted rounded-lg p-4">
                                    <p className="text-foreground text-sm leading-relaxed whitespace-pre-wrap">
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
