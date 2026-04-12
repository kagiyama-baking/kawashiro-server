import type { FormEvent } from 'react';
import { LoadingButton } from '@/components/common/LoadingButton';
import { Label } from '@/components/ui/label';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import type { GenerateConfig } from '@/types/talk';

interface GenerateFormProps {
    readonly configs: GenerateConfig[];
    readonly selectedConfig: string;
    readonly onConfigChange: (config: string) => void;
    readonly onSubmit: () => void;
    readonly isLoading: boolean;
}

export function GenerateForm({
    configs,
    selectedConfig,
    onConfigChange,
    onSubmit,
    isLoading,
}: GenerateFormProps) {
    const handleSubmit = (e: FormEvent) => {
        e.preventDefault();
        if (selectedConfig && !isLoading) {
            onSubmit();
        }
    };

    const selected = configs.find((c) => c.name === selectedConfig);

    return (
        <form onSubmit={handleSubmit} className="space-y-3.5">
            <div className="space-y-2">
                <Label
                    htmlFor="preset-select"
                    className="text-[13px] font-medium"
                >
                    プリセット
                </Label>
                <Select value={selectedConfig} onValueChange={onConfigChange}>
                    <SelectTrigger id="preset-select">
                        <SelectValue placeholder="設定を選択" />
                    </SelectTrigger>
                    <SelectContent>
                        {configs.map((config) => (
                            <SelectItem key={config.name} value={config.name}>
                                {config.display_name}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
                {selected && (
                    <div className="flex flex-wrap gap-2 text-xs">
                        {selected.use_datetime && (
                            <span className="rounded-md border border-[oklch(0.75_0.20_155/0.2)] bg-[oklch(0.75_0.20_155/0.08)] px-1.5 py-0.5 text-[oklch(0.75_0.20_155)]">
                                日時
                            </span>
                        )}
                        {selected.use_weather && (
                            <span className="rounded-md border border-[oklch(0.75_0.20_155/0.2)] bg-[oklch(0.75_0.20_155/0.08)] px-1.5 py-0.5 text-[oklch(0.75_0.20_155)]">
                                天気
                            </span>
                        )}
                        {selected.use_events && (
                            <span className="rounded-md border border-[oklch(0.75_0.20_155/0.2)] bg-[oklch(0.75_0.20_155/0.08)] px-1.5 py-0.5 text-[oklch(0.75_0.20_155)]">
                                予定
                            </span>
                        )}
                        {selected.tts_enabled && (
                            <span className="rounded-md border border-[oklch(0.72_0.20_155/0.2)] bg-[oklch(0.72_0.20_155/0.1)] px-1.5 py-0.5 text-[oklch(0.72_0.20_155)]">
                                TTS有効
                            </span>
                        )}
                    </div>
                )}
            </div>

            <p className="text-muted-foreground text-[12px] leading-relaxed">
                プロンプトはサーバー側（Langfuse）で管理されています。
                プリセットを選んで生成ボタンを押してください。
            </p>

            <LoadingButton
                type="submit"
                className="mt-1 w-full font-medium"
                isLoading={isLoading}
                loadingText="生成中..."
                disabled={!selectedConfig}
            >
                テキストを生成
            </LoadingButton>
        </form>
    );
}
