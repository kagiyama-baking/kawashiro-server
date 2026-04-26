import { Square } from 'lucide-react';
import type { FormEvent, KeyboardEvent } from 'react';
import { LoadingButton } from '@/components/common/LoadingButton';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { CHAT_MESSAGE_MAX_LENGTH } from '@/types/talk';

interface ChatInputFormProps {
    readonly input: string;
    readonly onInputChange: (value: string) => void;
    readonly onSubmit: () => void;
    readonly onCancel: () => void;
    readonly isLoading: boolean;
    readonly disabled?: boolean;
}

export function ChatInputForm({
    input,
    onInputChange,
    onSubmit,
    onCancel,
    isLoading,
    disabled = false,
}: ChatInputFormProps) {
    const length = input.length;
    const isOverLimit = length > CHAT_MESSAGE_MAX_LENGTH;
    const isEmpty = input.trim() === '';
    const cannotSubmit = disabled || isLoading || isOverLimit || isEmpty;

    const handleSubmit = (e: FormEvent) => {
        e.preventDefault();
        if (!cannotSubmit) onSubmit();
    };

    const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
        // IME 変換中の Enter は送信しない
        if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            if (!cannotSubmit) onSubmit();
        }
    };

    return (
        <form onSubmit={handleSubmit} className="space-y-2">
            <Textarea
                value={input}
                onChange={(e) => onInputChange(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="メッセージを入力（Enter で送信、Shift+Enter で改行）"
                rows={3}
                aria-invalid={isOverLimit || undefined}
                disabled={disabled || isLoading}
            />
            <div className="text-muted-foreground flex items-center justify-between text-[12px]">
                <span>
                    {disabled
                        ? 'プリセットを選択してください'
                        : isLoading
                          ? '生成中… 停止ボタンで中断できます'
                          : 'Enter で送信、Shift+Enter で改行'}
                </span>
                <span
                    className={
                        isOverLimit ? 'text-destructive font-medium' : undefined
                    }
                >
                    {length} / {CHAT_MESSAGE_MAX_LENGTH}
                </span>
            </div>
            <div className="flex justify-end">
                {isLoading ? (
                    <Button
                        type="button"
                        variant="destructive"
                        onClick={onCancel}
                    >
                        <Square
                            className="mr-1.5 h-4 w-4"
                            fill="currentColor"
                        />
                        停止
                    </Button>
                ) : (
                    <LoadingButton
                        type="submit"
                        isLoading={false}
                        disabled={cannotSubmit}
                    >
                        送信
                    </LoadingButton>
                )}
            </div>
        </form>
    );
}
