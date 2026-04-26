import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { formatBytes } from '@/lib/format/bytes';
import { cn } from '@/lib/utils';
import type { ChatSessionListItem as Item } from '@/types/talk';

interface SessionListItemProps {
    readonly item: Item;
    readonly isActive: boolean;
    readonly onSelect: (id: string) => void;
    readonly onDelete: (id: string) => void;
}

function formatDate(iso: string): string {
    const d = new Date(iso);
    const m = d.getMonth() + 1;
    const day = d.getDate();
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    return `${m}/${day} ${hh}:${mm}`;
}

export function SessionListItem({
    item,
    isActive,
    onSelect,
    onDelete,
}: SessionListItemProps) {
    const title = item.title || '（無題）';
    return (
        <button
            type="button"
            onClick={() => onSelect(item.id)}
            className={cn(
                'group relative w-full rounded-lg border px-3 py-2 text-left transition',
                'hover:bg-[oklch(0.95_0_0/0.05)]',
                isActive
                    ? 'border-[oklch(0.72_0.20_155/0.5)] bg-[oklch(0.72_0.20_155/0.10)]'
                    : 'border-[oklch(0.95_0_0/0.06)]',
            )}
        >
            <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium">{title}</p>
                    <div className="text-muted-foreground mt-0.5 flex items-center gap-1.5 text-[11px]">
                        <span>{formatDate(item.updated_at)}</span>
                        <span>·</span>
                        <span>{item.message_count} 件</span>
                        <span>·</span>
                        <span>{formatBytes(item.total_audio_bytes)}</span>
                    </div>
                </div>
                <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={(e) => {
                        e.stopPropagation();
                        onDelete(item.id);
                    }}
                    className="h-6 w-6 shrink-0 opacity-0 transition group-hover:opacity-100"
                    aria-label="セッションを削除"
                >
                    <Trash2 className="h-3.5 w-3.5" />
                </Button>
            </div>
        </button>
    );
}
