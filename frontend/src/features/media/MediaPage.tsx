import { Download } from 'lucide-react';
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ImageConverter } from './ImageConverter';
import { ZipToPdf } from './ZipToPdf';
import { useMedia } from './useMedia';

export function MediaPage() {
    const {
        result,
        isLoading,
        error,
        handleConvertImage,
        handleZipToPdf,
        downloadResult,
    } = useMedia();

    return (
        <div className="mx-auto max-w-4xl space-y-6">
            <div className="animate-slide-up">
                <h1 className="font-heading text-foreground text-2xl font-bold tracking-tight">
                    メディア変換
                </h1>
                <p className="text-muted-foreground mt-1 font-mono text-xs">
                    // image &amp; document conversion
                </p>
            </div>

            <Card className="animate-slide-up neon-border">
                <CardHeader>
                    <CardTitle className="font-heading font-semibold">
                        変換ツール
                    </CardTitle>
                    <CardDescription className="text-[13px]">
                        変換タイプを選択してファイルをアップロードしてください
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <Tabs defaultValue="image">
                        <TabsList className="mb-4">
                            <TabsTrigger value="image">
                                画像フォーマット変換
                            </TabsTrigger>
                            <TabsTrigger value="zip">ZIP → PDF</TabsTrigger>
                        </TabsList>
                        <TabsContent value="image">
                            <ImageConverter
                                onSubmit={handleConvertImage}
                                isLoading={isLoading}
                            />
                        </TabsContent>
                        <TabsContent value="zip">
                            <ZipToPdf
                                onSubmit={handleZipToPdf}
                                isLoading={isLoading}
                            />
                        </TabsContent>
                    </Tabs>

                    <ErrorMessage message={error} />

                    {result && (
                        <div className="animate-slide-up mt-4 space-y-3">
                            <Separator className="opacity-30" />
                            <div className="glass neon-border flex items-center justify-between rounded-xl p-4">
                                <span className="text-foreground font-mono text-sm">
                                    {result.filename}
                                </span>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="transition-all duration-200 hover:shadow-[0_0_12px_oklch(0.82_0.18_192/0.15)]"
                                    onClick={downloadResult}
                                >
                                    <Download className="mr-2 h-4 w-4" />
                                    ダウンロード
                                </Button>
                            </div>
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
