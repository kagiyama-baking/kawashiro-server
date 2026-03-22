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
            <div>
                <h1 className="text-2xl font-bold text-foreground">
                    メディア変換
                </h1>
                <p className="text-sm text-muted-foreground">
                    画像フォーマットの変換やZIPからPDFへの変換を行います
                </p>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle className="font-sans">変換ツール</CardTitle>
                    <CardDescription>
                        変換タイプを選択してファイルをアップロードしてください
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <Tabs defaultValue="image">
                        <TabsList className="mb-4">
                            <TabsTrigger value="image">
                                画像フォーマット変換
                            </TabsTrigger>
                            <TabsTrigger value="zip">
                                ZIP → PDF
                            </TabsTrigger>
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
                        <div className="mt-4 space-y-3">
                            <Separator />
                            <div className="flex items-center justify-between rounded-lg bg-muted p-3">
                                <span className="text-sm text-foreground">
                                    {result.filename}
                                </span>
                                <Button
                                    variant="outline"
                                    size="sm"
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
