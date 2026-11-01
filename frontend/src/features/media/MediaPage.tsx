import { Download } from 'lucide-react';
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
        <div className="max-w-(--page-max-width)">
            <PageHeader
                eyebrow="Media"
                title="メディア変換"
                lead="画像の形式を変換したり、ZIP にまとめた画像を PDF にします"
            />

            <Card>
                <CardHeader>
                    <CardTitle>変換ツール</CardTitle>
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
                            <Separator />
                            <div className="bg-secondary flex items-center justify-between gap-3 rounded-lg border p-4">
                                <span className="text-ink-strong min-w-0 text-sm wrap-anywhere">
                                    {result.filename}
                                </span>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={downloadResult}
                                >
                                    <Download />
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
