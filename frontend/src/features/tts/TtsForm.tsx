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
import { useTtsStore } from '@/stores/tts-store';

interface TtsFormProps {
    readonly models: string[];
    readonly styles: string[];
    readonly selectedModel: string;
    readonly onModelChange: (model: string) => void;
    readonly onSubmit: (text: string) => void;
    readonly isLoading: boolean;
}

export function TtsForm({
    models,
    styles,
    selectedModel,
    onModelChange,
    onSubmit,
    isLoading,
}: TtsFormProps) {
    const [text, setText] = useState('');
    const params = useTtsStore((s) => s.params);
    const setParam = useTtsStore((s) => s.setParam);
    const formRef = useRef<HTMLFormElement>(null);

    const handleSubmit = (e: FormEvent) => {
        e.preventDefault();
        if (text.trim() && !isLoading) {
            onSubmit(text);
        }
    };

    const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            formRef.current?.requestSubmit();
        }
    };

    return (
        <form ref={formRef} onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
                <Label htmlFor="tts-text">テキスト</Label>
                <Textarea
                    id="tts-text"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="読み上げたいテキストを入力...（Ctrl+Enterで送信）"
                    rows={4}
                    maxLength={500}
                    required
                />
                <p className="text-muted-foreground text-xs">
                    {text.length}/500文字
                </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                    <Label>モデル</Label>
                    <Select value={selectedModel} onValueChange={onModelChange}>
                        <SelectTrigger>
                            <SelectValue placeholder="モデルを選択" />
                        </SelectTrigger>
                        <SelectContent>
                            {models.map((model) => (
                                <SelectItem key={model} value={model}>
                                    {model}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>

                <div className="space-y-2">
                    <Label>スタイル</Label>
                    <Select
                        value={params.style}
                        onValueChange={(v) => setParam('style', v)}
                    >
                        <SelectTrigger>
                            <SelectValue placeholder="スタイルを選択" />
                        </SelectTrigger>
                        <SelectContent>
                            {styles.map((style) => (
                                <SelectItem key={style} value={style}>
                                    {style}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>
            </div>

            <div className="grid grid-cols-3 gap-4">
                <div className="space-y-2">
                    <Label>出力形式</Label>
                    <Select
                        value={params.format}
                        onValueChange={(v) =>
                            setParam('format', v as 'wav' | 'mp3' | 'ogg')
                        }
                    >
                        <SelectTrigger>
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="wav">WAV</SelectItem>
                            <SelectItem value="mp3">MP3</SelectItem>
                            <SelectItem value="ogg">OGG</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            </div>

            <LoadingButton
                type="submit"
                className="w-full"
                isLoading={isLoading}
                loadingText="合成中..."
                disabled={!text.trim()}
            >
                音声を生成
            </LoadingButton>
        </form>
    );
}
