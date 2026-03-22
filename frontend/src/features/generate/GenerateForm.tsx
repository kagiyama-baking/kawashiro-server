import { type FormEvent, type KeyboardEvent, useRef, useState } from 'react';
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
import type { GenerateConfig } from '@/types/generate';

interface GenerateFormProps {
    readonly configs: GenerateConfig[];
    readonly selectedConfig: string;
    readonly onConfigChange: (config: string) => void;
    readonly onSubmit: (userPrompt: string) => void;
    readonly isLoading: boolean;
}

export function GenerateForm({
    configs,
    selectedConfig,
    onConfigChange,
    onSubmit,
    isLoading,
}: GenerateFormProps) {
    const [userPrompt, setUserPrompt] = useState('');
    const formRef = useRef<HTMLFormElement>(null);

    const handleSubmit = (e: FormEvent) => {
        e.preventDefault();
        if (userPrompt.trim() && selectedConfig && !isLoading) {
            onSubmit(userPrompt);
        }
    };

    const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            formRef.current?.requestSubmit();
        }
    };

    const selected = configs.find((c) => c.name === selectedConfig);

    return (
        <form ref={formRef} onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
                <Label>プリセット</Label>
                <Select value={selectedConfig} onValueChange={onConfigChange}>
                    <SelectTrigger>
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
                    <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                        {selected.use_datetime && (
                            <span className="rounded bg-muted px-2 py-0.5">
                                日時
                            </span>
                        )}
                        {selected.use_weather && (
                            <span className="rounded bg-muted px-2 py-0.5">
                                天気
                            </span>
                        )}
                        {selected.use_events && (
                            <span className="rounded bg-muted px-2 py-0.5">
                                予定
                            </span>
                        )}
                        {selected.tts_enabled && (
                            <span className="rounded bg-primary/20 px-2 py-0.5 text-primary">
                                TTS有効
                            </span>
                        )}
                    </div>
                )}
            </div>

            <div className="space-y-2">
                <Label htmlFor="user-prompt">ユーザープロンプト</Label>
                <Textarea
                    id="user-prompt"
                    value={userPrompt}
                    onChange={(e) => setUserPrompt(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="プロンプトを入力...（Ctrl+Enterで送信）"
                    rows={5}
                    required
                />
            </div>

            <LoadingButton
                type="submit"
                className="w-full"
                isLoading={isLoading}
                loadingText="生成中..."
                disabled={!userPrompt.trim() || !selectedConfig}
            >
                テキストを生成
            </LoadingButton>
        </form>
    );
}
