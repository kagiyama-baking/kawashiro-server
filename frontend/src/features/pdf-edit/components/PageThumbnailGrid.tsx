import {
    DndContext,
    type DragEndEvent,
    DragOverlay,
    type DragStartEvent,
    KeyboardSensor,
    PointerSensor,
    closestCenter,
    useSensor,
    useSensors,
} from '@dnd-kit/core';
import {
    SortableContext,
    rectSortingStrategy,
    sortableKeyboardCoordinates,
    useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, Layers } from 'lucide-react';
import { type MouseEvent, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { usePdfEditStore } from '@/stores/pdf-edit-store';
import type { PageState, SourcePageInfo } from '@/types/pdf-edit';
import { PageThumbnailItem } from './PageThumbnailItem';

interface PageThumbnailGridProps {
    readonly sources: readonly SourcePageInfo[];
}

interface SortableThumbnailProps {
    readonly page: PageState;
    readonly displayIndex: number;
    readonly source: SourcePageInfo;
    readonly isSelected: boolean;
    readonly isGhost: boolean;
    readonly onClick: (event: MouseEvent<HTMLDivElement>, id: string) => void;
    readonly onToggle: (id: string) => void;
}

function SortableThumbnail({
    page,
    displayIndex,
    source,
    isSelected,
    isGhost,
    onClick,
    onToggle,
}: SortableThumbnailProps) {
    const {
        attributes,
        listeners,
        setNodeRef,
        transform,
        transition,
        isDragging,
    } = useSortable({ id: page.id });

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isGhost || isDragging ? 0.3 : 1,
    };

    return (
        <div ref={setNodeRef} style={style} className="group relative">
            <PageThumbnailItem
                page={page}
                displayIndex={displayIndex}
                source={source}
                isSelected={isSelected}
                onClick={onClick}
                onToggle={onToggle}
            />
            {/* ドラッグハンドル：選択中はグループ全体、未選択は単独で動かす */}
            <button
                type="button"
                aria-label={`ページ ${displayIndex} をドラッグ`}
                {...attributes}
                {...listeners}
                className={cn(
                    'glass absolute top-1 right-10 cursor-grab rounded p-1 opacity-0 transition-opacity',
                    'group-hover:opacity-100 active:cursor-grabbing',
                    'hover:bg-[oklch(0.75_0.20_155/0.2)]',
                )}
            >
                <GripVertical className="h-3.5 w-3.5" />
            </button>
        </div>
    );
}

export function PageThumbnailGrid({ sources }: PageThumbnailGridProps) {
    const pages = usePdfEditStore((s) => s.pages);
    const selection = usePdfEditStore((s) => s.selection);
    const selectOnly = usePdfEditStore((s) => s.selectOnly);
    const toggleSelection = usePdfEditStore((s) => s.toggleSelection);
    const selectRange = usePdfEditStore((s) => s.selectRange);
    const reorder = usePdfEditStore((s) => s.reorder);

    const [draggingIds, setDraggingIds] = useState<readonly string[]>([]);
    const [activeId, setActiveId] = useState<string | null>(null);

    const sensors = useSensors(
        useSensor(PointerSensor, {
            // クリック選択とドラッグを区別するための最小移動距離
            activationConstraint: { distance: 5 },
        }),
        useSensor(KeyboardSensor, {
            coordinateGetter: sortableKeyboardCoordinates,
        }),
    );

    const sourceMap = useMemo(() => {
        const m = new Map<number, SourcePageInfo>();
        for (const s of sources) m.set(s.sourceIndex, s);
        return m;
    }, [sources]);

    const handleClick = (e: MouseEvent<HTMLDivElement>, id: string) => {
        if (e.shiftKey) {
            selectRange(id);
        } else if (e.ctrlKey || e.metaKey) {
            toggleSelection(id);
        } else {
            selectOnly(id);
        }
    };

    const handleDragStart = (event: DragStartEvent) => {
        const id = String(event.active.id);
        setActiveId(id);
        // dragする要素が選択集合に含まれていたら、選択集合全体を一緒に動かす
        if (selection.has(id) && selection.size > 1) {
            setDraggingIds(Array.from(selection));
        } else {
            setDraggingIds([id]);
        }
    };

    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event;
        const dragging = draggingIds;
        setDraggingIds([]);
        setActiveId(null);

        if (!over) return;
        if (active.id === over.id && dragging.length === 1) return;

        const draggingSet = new Set(dragging);
        // ドロップ先が ドラッグ中の集合内 の場合は何もしない
        if (draggingSet.has(String(over.id)) && active.id !== over.id) {
            return;
        }

        const remaining = pages.filter((p) => !draggingSet.has(p.id));
        const overIndex = remaining.findIndex((p) => p.id === over.id);
        if (overIndex === -1) return;

        // active と over の元の位置関係でinsert位置を補正
        const originalActiveIndex = pages.findIndex((p) => p.id === active.id);
        const originalOverIndex = pages.findIndex((p) => p.id === over.id);
        const insertIndex =
            originalActiveIndex < originalOverIndex ? overIndex + 1 : overIndex;

        const draggingPages = pages.filter((p) => draggingSet.has(p.id));
        const newOrder = [
            ...remaining.slice(0, insertIndex),
            ...draggingPages,
            ...remaining.slice(insertIndex),
        ];
        reorder(newOrder.map((p) => p.id));
    };

    const handleDragCancel = () => {
        setDraggingIds([]);
        setActiveId(null);
    };

    if (pages.length === 0) return null;

    const ghostSet = new Set(
        draggingIds.length > 1
            ? draggingIds.filter((id) => id !== activeId)
            : [],
    );

    return (
        <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
            onDragCancel={handleDragCancel}
        >
            <SortableContext
                items={pages.map((p) => p.id)}
                strategy={rectSortingStrategy}
            >
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
                    {pages.map((page, idx) => {
                        const source = sourceMap.get(page.sourceIndex);
                        if (!source) return null;
                        return (
                            <SortableThumbnail
                                key={page.id}
                                page={page}
                                displayIndex={idx + 1}
                                source={source}
                                isSelected={selection.has(page.id)}
                                isGhost={ghostSet.has(page.id)}
                                onClick={handleClick}
                                onToggle={toggleSelection}
                            />
                        );
                    })}
                </div>
            </SortableContext>
            <DragOverlay>
                {draggingIds.length > 0 && activeId
                    ? renderDragOverlay(
                          draggingIds.length,
                          pages,
                          activeId,
                          sourceMap,
                      )
                    : null}
            </DragOverlay>
        </DndContext>
    );
}

function renderDragOverlay(
    count: number,
    pages: readonly PageState[],
    activeId: string,
    sourceMap: ReadonlyMap<number, SourcePageInfo>,
) {
    const active = pages.find((p) => p.id === activeId);
    if (!active) return null;
    const source = sourceMap.get(active.sourceIndex);
    if (!source) return null;
    const halfStyle =
        active.splitHalf === 'left'
            ? { clipPath: 'inset(0 50% 0 0)' }
            : active.splitHalf === 'right'
              ? { clipPath: 'inset(0 0 0 50%)' }
              : undefined;
    return (
        <div className="glass neon-border relative w-32 cursor-grabbing rounded-xl p-2 shadow-[0_0_24px_oklch(0.75_0.20_155/0.5)]">
            <div className="bg-background/50 flex aspect-[3/4] items-center justify-center overflow-hidden rounded-lg">
                <div
                    className="flex h-full w-full items-center justify-center"
                    style={halfStyle}
                >
                    <img
                        src={source.thumbnailUrl}
                        alt=""
                        className="max-h-full max-w-full object-contain"
                        draggable={false}
                    />
                </div>
            </div>
            {count > 1 && (
                <div className="bg-background/90 text-foreground absolute -top-2 -right-2 flex items-center gap-1 rounded-full px-2 py-1 font-mono text-[11px] shadow-md">
                    <Layers className="h-3 w-3" />
                    {count}
                </div>
            )}
        </div>
    );
}
