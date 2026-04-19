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
import { Textarea } from '@/components/ui/textarea';
import { USER_PROMPT_MAX_LENGTH, type GenerateConfig } from '@/types/talk';

interface GenerateFormProps {
    readonly configs: GenerateConfig[];
    readonly selectedConfig: string;
    readonly onConfigChange: (config: string) => void;
    readonly userPrompt: string;
    readonly onUserPromptChange: (value: string) => void;
    readonly onSubmit: () => void;
    readonly isLoading: boolean;
}

export function GenerateForm({
    configs,
    selectedConfig,
    onConfigChange,
    userPrompt,
    onUserPromptChange,
    onSubmit,
    isLoading,
}: GenerateFormProps) {
    const selected = configs.find((c) => c.name === selectedConfig);
    const promptLength = userPrompt.length;
    const isOverLimit = promptLength > USER_PROMPT_MAX_LENGTH;

    const handleSubmit = (e: FormEvent) => {
        e.preventDefault();
        if (selectedConfig && !isLoading && !isOverLimit) {
            onSubmit();
        }
    };

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
                {selected?.tts_enabled && (
                    <div className="flex flex-wrap gap-2 text-xs">
                        <span className="rounded-md border border-[oklch(0.72_0.20_155/0.2)] bg-[oklch(0.72_0.20_155/0.1)] px-1.5 py-0.5 text-[oklch(0.72_0.20_155)]">
                            TTS有効
                        </span>
                    </div>
                )}
            </div>

            <div className="space-y-2">
                <Label
                    htmlFor="user-prompt"
                    className="text-[13px] font-medium"
                >
                    カスタムユーザープロンプト（任意）
                </Label>
                <Textarea
                    id="user-prompt"
                    value={userPrompt}
                    onChange={(e) => onUserPromptChange(e.target.value)}
                    placeholder="例: 今日は {{datetime}} です。一言お願いします。"
                    rows={4}
                    aria-invalid={isOverLimit || undefined}
                    aria-describedby="user-prompt-help"
                />
                <div
                    id="user-prompt-help"
                    className="text-muted-foreground flex items-center justify-between text-[12px] leading-relaxed"
                >
                    <span>
                        利用可能: <code>{'{{datetime}}'}</code>{' '}
                        <code>{'{{weather}}'}</code> <code>{'{{events}}'}</code>
                    </span>
                    <span
                        className={
                            isOverLimit
                                ? 'text-destructive font-medium'
                                : undefined
                        }
                    >
                        {promptLength} / {USER_PROMPT_MAX_LENGTH}
                    </span>
                </div>
            </div>

            <p className="text-muted-foreground text-[12px] leading-relaxed">
                未入力ならサーバー側（Langfuse）のプロンプトを使用します。
            </p>

            <LoadingButton
                type="submit"
                className="mt-1 w-full font-medium"
                isLoading={isLoading}
                loadingText="生成中..."
                disabled={!selectedConfig || isOverLimit}
            >
                テキストを生成
            </LoadingButton>
        </form>
    );
}
