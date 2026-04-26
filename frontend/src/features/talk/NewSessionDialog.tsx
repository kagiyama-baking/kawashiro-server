import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import type { GenerateConfig } from '@/types/talk';

interface NewSessionDialogProps {
    readonly configs: GenerateConfig[];
    readonly open: boolean;
    readonly onClose: () => void;
    readonly onCreate: (configName: string) => Promise<void>;
}

export function NewSessionDialog({
    configs,
    open,
    onClose,
    onCreate,
}: NewSessionDialogProps) {
    const [selected, setSelected] = useState<string>(configs[0]?.name ?? '');
    const [isCreating, setIsCreating] = useState(false);

    if (!open) return null;

    const handleCreate = async () => {
        if (!selected || isCreating) return;
        setIsCreating(true);
        try {
            await onCreate(selected);
            onClose();
        } finally {
            setIsCreating(false);
        }
    };

    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
            onClick={onClose}
            role="presentation"
        >
            <div
                className="bg-background w-full max-w-md rounded-xl border border-[oklch(0.95_0_0/0.1)] p-5 shadow-xl"
                onClick={(e) => e.stopPropagation()}
                role="dialog"
                aria-modal="true"
            >
                <h2 className="font-heading text-foreground mb-1 text-lg font-semibold">
                    新しいチャット
                </h2>
                <p className="text-muted-foreground mb-4 text-[13px]">
                    使用するプリセットを選択してください。途中で変更はできません。
                </p>

                <div className="space-y-2">
                    <Label htmlFor="new-session-preset" className="text-[13px]">
                        プリセット
                    </Label>
                    <Select value={selected} onValueChange={setSelected}>
                        <SelectTrigger id="new-session-preset">
                            <SelectValue placeholder="設定を選択" />
                        </SelectTrigger>
                        <SelectContent>
                            {configs.map((c) => (
                                <SelectItem key={c.name} value={c.name}>
                                    {c.display_name}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>

                <div className="mt-5 flex justify-end gap-2">
                    <Button
                        type="button"
                        variant="ghost"
                        onClick={onClose}
                        disabled={isCreating}
                    >
                        キャンセル
                    </Button>
                    <Button
                        type="button"
                        onClick={handleCreate}
                        disabled={!selected || isCreating}
                    >
                        {isCreating ? '作成中…' : '作成'}
                    </Button>
                </div>
            </div>
        </div>
    );
}
