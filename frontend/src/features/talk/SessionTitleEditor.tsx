import { Check, Pencil, X } from 'lucide-react';
import { type KeyboardEvent, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface SessionTitleEditorProps {
    readonly title: string;
    readonly onSave: (title: string) => Promise<void>;
}

export function SessionTitleEditor({ title, onSave }: SessionTitleEditorProps) {
    const [isEditing, setIsEditing] = useState(false);
    const [draft, setDraft] = useState(title);
    const [isSaving, setIsSaving] = useState(false);

    const start = () => {
        setDraft(title);
        setIsEditing(true);
    };
    const cancel = () => {
        setDraft(title);
        setIsEditing(false);
    };
    const save = async () => {
        const next = draft.trim();
        if (!next || isSaving) {
            cancel();
            return;
        }
        setIsSaving(true);
        try {
            await onSave(next);
        } finally {
            setIsSaving(false);
            setIsEditing(false);
        }
    };
    const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter') save();
        if (e.key === 'Escape') cancel();
    };

    if (isEditing) {
        return (
            <div className="flex items-center gap-1">
                <Input
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={handleKeyDown}
                    autoFocus
                    maxLength={120}
                    className="h-8 text-[14px]"
                />
                <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    onClick={save}
                    disabled={isSaving}
                    className="h-8 w-8"
                    aria-label="保存"
                >
                    <Check className="h-4 w-4" />
                </Button>
                <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    onClick={cancel}
                    disabled={isSaving}
                    className="h-8 w-8"
                    aria-label="キャンセル"
                >
                    <X className="h-4 w-4" />
                </Button>
            </div>
        );
    }

    return (
        <div className="flex items-center gap-2">
            <h2 className="font-heading truncate text-[16px] font-semibold">
                {title || '（無題）'}
            </h2>
            <Button
                type="button"
                size="icon"
                variant="ghost"
                onClick={start}
                className="h-7 w-7"
                aria-label="タイトルを編集"
            >
                <Pencil className="h-3.5 w-3.5" />
            </Button>
        </div>
    );
}
