import { Trash2 } from 'lucide-react';
import { NavLink } from 'react-router';
import { GHOST_ON_SIDEBAR } from '@/components/layout/sidebar-styles';
import { Button } from '@/components/ui/button';
import { formatBytes } from '@/lib/format/bytes';
import { cn } from '@/lib/utils';
import type { ChatSessionListItem as Item } from '@/types/talk';

interface SessionListItemProps {
    readonly item: Item;
    readonly onDelete: (item: Item) => void;
    readonly onNavigate?: () => void;
}

function formatDate(iso: string): string {
    const d = new Date(iso);
    const m = d.getMonth() + 1;
    const day = d.getDate();
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    return `${m}/${day} ${hh}:${mm}`;
}

/** 一覧の 1 行。リンクと削除ボタンは兄弟に置く（入れ子にすると HTML として不正になる）。 */
export function SessionListItem({
    item,
    onDelete,
    onNavigate,
}: SessionListItemProps) {
    const title = item.title || '（無題）';
    return (
        <li className="group relative">
            <NavLink
                to={`/talk/${item.id}`}
                onClick={onNavigate}
                className="text-sidebar-muted-foreground before:bg-sidebar-primary hover:bg-sidebar-hover hover:text-sidebar-accent-foreground aria-[current=page]:bg-sidebar-accent aria-[current=page]:text-sidebar-accent-foreground relative block rounded-md py-[0.45rem] pr-8 pl-4 transition-colors before:absolute before:top-1/2 before:left-0 before:h-0 before:w-0.5 before:-translate-y-1/2 before:transition-[height] aria-[current=page]:before:h-[62%]"
            >
                <span className="block truncate text-[0.8rem] leading-[1.5] tracking-[0.02em]">
                    {title}
                </span>
                <span className="font-latin block truncate text-[0.66rem] leading-[1.5] tracking-[0.02em] opacity-78">
                    {formatDate(item.updated_at)} · {item.message_count} 件 ·{' '}
                    {formatBytes(item.total_audio_bytes)}
                </span>
            </NavLink>
            {/* マウスでは行に乗せたときだけ出す。タッチでは常に出して削除できるようにする */}
            <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                onClick={() => onDelete(item)}
                className={cn(
                    GHOST_ON_SIDEBAR,
                    'absolute top-1/2 right-1 -translate-y-1/2 transition-[opacity,color,background-color] [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-focus-within:opacity-100 [@media(hover:hover)]:group-hover:opacity-100',
                )}
                aria-label={`「${title}」を削除`}
            >
                <Trash2 className="size-3.5" />
            </Button>
        </li>
    );
}
