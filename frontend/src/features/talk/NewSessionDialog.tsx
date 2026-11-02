import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
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
        <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
            <DialogContent>
                <DialogHeader>
                    <DialogTitle>新しいチャット</DialogTitle>
                    <DialogDescription>
                        使用するプリセットを選択してください。途中で変更はできません。
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-2">
                    <Label htmlFor="new-session-preset">プリセット</Label>
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

                <DialogFooter>
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
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
