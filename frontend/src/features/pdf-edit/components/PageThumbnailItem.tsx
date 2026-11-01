import { Crop, SplitSquareHorizontal } from 'lucide-react';
import type { MouseEvent } from 'react';
import { Checkbox } from '@/components/ui/checkbox';
import { cn } from '@/lib/utils';
import type { PageState, SourcePageInfo } from '@/types/pdf-edit';

interface PageThumbnailItemProps {
    readonly page: PageState;
    readonly displayIndex: number;
    readonly source: SourcePageInfo;
    readonly isSelected: boolean;
    readonly onClick: (event: MouseEvent<HTMLDivElement>, id: string) => void;
    readonly onToggle: (id: string) => void;
}

/**
 * ページサムネイル1枚。
 *
 * - 選択中は緑の枠で強調
 * - 左上のチェックボックスで明示的に複数選択（クリックの伝播を止める）
 * - 分割（左/右）はサムネをCSSでクリッピングして表現
 * - トリミング（crop）は枠線オーバーレイで可視化
 * - サムネ本体クリック時はShift/Ctrl修飾キーを親に渡して選択ロジックを委譲
 */
export function PageThumbnailItem({
    page,
    displayIndex,
    source,
    isSelected,
    onClick,
    onToggle,
}: PageThumbnailItemProps) {
    const halfStyle =
        page.splitHalf === 'left'
            ? { clipPath: 'inset(0 50% 0 0)' }
            : page.splitHalf === 'right'
              ? { clipPath: 'inset(0 0 0 50%)' }
              : undefined;

    return (
        <div
            role="button"
            tabIndex={0}
            aria-pressed={isSelected}
            aria-label={`ページ ${displayIndex} を選択`}
            onClick={(e) => onClick(e, page.id)}
            onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onClick(
                        e as unknown as MouseEvent<HTMLDivElement>,
                        page.id,
                    );
                }
            }}
            className={cn(
                'bg-secondary group relative flex cursor-pointer flex-col overflow-hidden rounded-lg border p-2 transition-colors select-none',
                isSelected ? 'border-primary' : 'hover:border-input',
            )}
        >
            <div className="bg-background relative flex aspect-[3/4] items-center justify-center overflow-hidden rounded-md">
                <div
                    className="flex h-full w-full items-center justify-center"
                    style={halfStyle}
                >
                    <img
                        src={source.thumbnailUrl}
                        alt={`ページ ${displayIndex}`}
                        className="max-h-full max-w-full object-contain"
                        draggable={false}
                    />
                </div>
                {/* トリム枠の可視化 */}
                {page.crop && (
                    <div
                        className="border-primary pointer-events-none absolute border-2"
                        style={{
                            left: `${page.crop.x * 100}%`,
                            top: `${page.crop.y * 100}%`,
                            width: `${page.crop.width * 100}%`,
                            height: `${page.crop.height * 100}%`,
                        }}
                    />
                )}
                {/* 編集マーカー（右上） */}
                <div className="absolute top-1 right-1 flex gap-1">
                    {page.splitHalf && (
                        <span
                            className="bg-background/80 text-foreground block rounded-sm px-1 py-0.5"
                            title={
                                page.splitHalf === 'left' ? '左半分' : '右半分'
                            }
                        >
                            <SplitSquareHorizontal className="h-3 w-3" />
                        </span>
                    )}
                    {page.crop && (
                        <span
                            className="bg-background/80 text-foreground block rounded-sm px-1 py-0.5"
                            title="トリミング適用済み"
                        >
                            <Crop className="h-3 w-3" />
                        </span>
                    )}
                </div>
            </div>

            {/* 選択チェックボックス（左上にオーバーレイ）。
                選択中またはhoverで常時表示。クリックは伝播を止めて
                サムネ本体の単一選択挙動と衝突しないようにする。 */}
            <div
                className={cn(
                    'absolute top-2.5 left-2.5 z-10 transition-opacity',
                    isSelected
                        ? 'opacity-100'
                        : 'opacity-0 group-focus-within:opacity-100 group-hover:opacity-100',
                )}
                onClick={(e) => e.stopPropagation()}
                onMouseDown={(e) => e.stopPropagation()}
                onKeyDown={(e) => e.stopPropagation()}
                role="presentation"
            >
                <Checkbox
                    checked={isSelected}
                    onCheckedChange={() => onToggle(page.id)}
                    aria-label={`ページ ${displayIndex} の選択をトグル`}
                    className="h-5 w-5"
                />
            </div>

            <p className="font-latin text-ink-subtle mt-2 text-center text-xs tabular-nums">
                {displayIndex}
            </p>
        </div>
    );
}
