/**
 * PDF編集の状態管理（zustand）
 *
 * 設計方針:
 * - 編集状態は「現在の最終ページ配列 (`pages`)」として保持（操作キューではなくスナップショット）。
 *   これによりサムネイル表示が `pages` をそのまま map すればよく、再計算が不要。
 * - 履歴は `pages` 配列のみを積む（選択は履歴に含めない）。最大 20 件、先頭から切り捨て。
 * - 選択は Set<id> で持ち、Shift+クリックの起点として `selectionAnchor` を別途保持する。
 */
import { create } from 'zustand';
import type { CropRect, PageState, SourcePageInfo } from '@/types/pdf-edit';

const MAX_HISTORY = 20;

interface PdfEditState {
    readonly pages: readonly PageState[];
    readonly selection: ReadonlySet<string>;
    readonly selectionAnchor: string | null;
    readonly history: ReadonlyArray<readonly PageState[]>;
    readonly historyIndex: number;

    readonly initFromSource: (source: readonly SourcePageInfo[]) => void;
    readonly selectOnly: (id: string) => void;
    readonly toggleSelection: (id: string) => void;
    readonly selectRange: (targetId: string) => void;
    readonly selectAll: () => void;
    readonly clearSelection: () => void;
    readonly deleteSelected: () => void;
    readonly reorder: (orderedIds: readonly string[]) => void;
    readonly splitSelected: () => void;
    readonly cropSelected: (crop: CropRect) => void;
    readonly clearCropSelected: () => void;
    readonly undo: () => void;
    readonly redo: () => void;
    readonly canUndo: () => boolean;
    readonly canRedo: () => boolean;
    readonly reset: () => void;
}

function generateId(): string {
    if (
        typeof globalThis.crypto !== 'undefined' &&
        typeof globalThis.crypto.randomUUID === 'function'
    ) {
        return globalThis.crypto.randomUUID();
    }
    // 万一 randomUUID 非対応の環境でもユニークになるフォールバック
    return `id-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function pushHistory(
    history: ReadonlyArray<readonly PageState[]>,
    historyIndex: number,
    newPages: readonly PageState[],
): {
    history: ReadonlyArray<readonly PageState[]>;
    historyIndex: number;
} {
    // 現在地より後ろのredo履歴を破棄してから追加
    const truncated = history.slice(0, historyIndex + 1);
    const next = [...truncated, newPages];
    while (next.length > MAX_HISTORY) next.shift();
    return { history: next, historyIndex: next.length - 1 };
}

export const usePdfEditStore = create<PdfEditState>((set, get) => ({
    pages: [],
    selection: new Set<string>(),
    selectionAnchor: null,
    history: [],
    historyIndex: -1,

    initFromSource: (source) => {
        const pages: PageState[] = source.map((s) => ({
            id: generateId(),
            sourceIndex: s.sourceIndex,
            splitHalf: null,
            crop: null,
        }));
        set({
            pages,
            selection: new Set<string>(),
            selectionAnchor: null,
            history: [pages],
            historyIndex: 0,
        });
    },

    selectOnly: (id) => {
        set({
            selection: new Set([id]),
            selectionAnchor: id,
        });
    },

    toggleSelection: (id) => {
        const next = new Set(get().selection);
        if (next.has(id)) {
            next.delete(id);
        } else {
            next.add(id);
        }
        set({ selection: next, selectionAnchor: id });
    },

    selectRange: (targetId) => {
        const { pages, selectionAnchor } = get();
        if (!selectionAnchor) {
            set({
                selection: new Set([targetId]),
                selectionAnchor: targetId,
            });
            return;
        }
        const anchorIndex = pages.findIndex((p) => p.id === selectionAnchor);
        const targetIndex = pages.findIndex((p) => p.id === targetId);
        if (anchorIndex === -1 || targetIndex === -1) return;
        const [from, to] =
            anchorIndex <= targetIndex
                ? [anchorIndex, targetIndex]
                : [targetIndex, anchorIndex];
        const next = new Set<string>();
        for (let i = from; i <= to; i++) {
            next.add(pages[i].id);
        }
        set({ selection: next });
    },

    selectAll: () => {
        const { pages } = get();
        set({ selection: new Set(pages.map((p) => p.id)) });
    },

    clearSelection: () => {
        set({ selection: new Set<string>(), selectionAnchor: null });
    },

    deleteSelected: () => {
        const { pages, selection, history, historyIndex } = get();
        if (selection.size === 0) return;
        const newPages = pages.filter((p) => !selection.has(p.id));
        const next = pushHistory(history, historyIndex, newPages);
        set({
            pages: newPages,
            selection: new Set<string>(),
            selectionAnchor: null,
            ...next,
        });
    },

    reorder: (orderedIds) => {
        const { pages, history, historyIndex } = get();
        const idToPage = new Map(pages.map((p) => [p.id, p]));
        const newPages: PageState[] = [];
        for (const id of orderedIds) {
            const page = idToPage.get(id);
            if (page) newPages.push(page);
        }
        // 渡されなかったページは末尾に維持（保険）
        for (const page of pages) {
            if (!orderedIds.includes(page.id)) newPages.push(page);
        }
        // 並びが変わっていなければ履歴に積まない
        const sameOrder =
            newPages.length === pages.length &&
            newPages.every((p, i) => p.id === pages[i].id);
        if (sameOrder) return;
        const next = pushHistory(history, historyIndex, newPages);
        set({ pages: newPages, ...next });
    },

    splitSelected: () => {
        const { pages, selection, history, historyIndex } = get();
        if (selection.size === 0) return;
        // 分割対象（選択中かつ未分割）が1つもなければ早期 return（履歴も増やさない）
        const hasTarget = pages.some(
            (p) => selection.has(p.id) && p.splitHalf === null,
        );
        if (!hasTarget) return;

        const newPages: PageState[] = [];
        for (const page of pages) {
            // 選択外、または既に分割済みのページはそのまま
            if (!selection.has(page.id) || page.splitHalf !== null) {
                newPages.push(page);
                continue;
            }
            // 左→右の順で2ページに展開（見開きスキャンを左綴じ書籍として扱う）
            newPages.push({
                ...page,
                id: generateId(),
                splitHalf: 'left',
            });
            newPages.push({
                ...page,
                id: generateId(),
                splitHalf: 'right',
            });
        }
        const next = pushHistory(history, historyIndex, newPages);
        set({
            pages: newPages,
            selection: new Set<string>(),
            selectionAnchor: null,
            ...next,
        });
    },

    cropSelected: (crop) => {
        const { pages, selection, history, historyIndex } = get();
        if (selection.size === 0) return;
        const newPages = pages.map((page) =>
            selection.has(page.id) ? { ...page, crop } : page,
        );
        const next = pushHistory(history, historyIndex, newPages);
        set({ pages: newPages, ...next });
    },

    clearCropSelected: () => {
        const { pages, selection, history, historyIndex } = get();
        if (selection.size === 0) return;
        const hasTarget = pages.some(
            (p) => selection.has(p.id) && p.crop !== null,
        );
        if (!hasTarget) return;
        const newPages = pages.map((page) =>
            selection.has(page.id) && page.crop !== null
                ? { ...page, crop: null }
                : page,
        );
        const next = pushHistory(history, historyIndex, newPages);
        set({ pages: newPages, ...next });
    },

    undo: () => {
        const { history, historyIndex } = get();
        if (historyIndex <= 0) return;
        const newIndex = historyIndex - 1;
        set({
            pages: history[newIndex],
            historyIndex: newIndex,
            selection: new Set<string>(),
            selectionAnchor: null,
        });
    },

    redo: () => {
        const { history, historyIndex } = get();
        if (historyIndex >= history.length - 1) return;
        const newIndex = historyIndex + 1;
        set({
            pages: history[newIndex],
            historyIndex: newIndex,
            selection: new Set<string>(),
            selectionAnchor: null,
        });
    },

    canUndo: () => get().historyIndex > 0,
    canRedo: () => {
        const { history, historyIndex } = get();
        return historyIndex < history.length - 1;
    },

    reset: () => {
        set({
            pages: [],
            selection: new Set<string>(),
            selectionAnchor: null,
            history: [],
            historyIndex: -1,
        });
    },
}));
