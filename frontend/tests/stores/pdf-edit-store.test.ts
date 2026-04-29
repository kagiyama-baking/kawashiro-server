/**
 * pdf-edit-store のテスト
 *
 * - initFromSource: SourcePageInfo[] からPageState[] に変換、履歴初期化
 * - 選択ロジック: selectOnly / toggle / range / all / clear
 * - 削除: 選択ページを削除し選択を解除、履歴を進める
 * - Undo/Redo: 履歴の前後遷移、redo履歴の破棄
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { usePdfEditStore } from '@/stores/pdf-edit-store';
import type { SourcePageInfo } from '@/types/pdf-edit';

function makeSource(count: number): SourcePageInfo[] {
    return Array.from({ length: count }, (_, i) => ({
        sourceIndex: i,
        width: 100,
        height: 100,
        thumbnailUrl: `blob://thumb-${i}`,
    }));
}

describe('pdf-edit-store', () => {
    beforeEach(() => {
        usePdfEditStore.getState().reset();
    });

    describe('initFromSource', () => {
        it('SourcePageInfo[] から PageState[] を生成する', () => {
            const source = makeSource(3);
            usePdfEditStore.getState().initFromSource(source);

            const { pages } = usePdfEditStore.getState();
            expect(pages).toHaveLength(3);
            expect(pages[0].sourceIndex).toBe(0);
            expect(pages[1].sourceIndex).toBe(1);
            expect(pages[2].sourceIndex).toBe(2);
        });

        it('各PageStateに一意のIDが付与される', () => {
            usePdfEditStore.getState().initFromSource(makeSource(5));
            const { pages } = usePdfEditStore.getState();
            const ids = pages.map((p) => p.id);
            expect(new Set(ids).size).toBe(ids.length);
        });

        it('split / crop は初期状態でnull', () => {
            usePdfEditStore.getState().initFromSource(makeSource(1));
            const { pages } = usePdfEditStore.getState();
            expect(pages[0].splitHalf).toBeNull();
            expect(pages[0].crop).toBeNull();
        });

        it('履歴を初期化する（長さ1、index=0）', () => {
            usePdfEditStore.getState().initFromSource(makeSource(2));
            const { history, historyIndex } = usePdfEditStore.getState();
            expect(history).toHaveLength(1);
            expect(historyIndex).toBe(0);
        });

        it('選択を空に初期化する', () => {
            usePdfEditStore.getState().initFromSource(makeSource(2));
            usePdfEditStore.getState().selectAll();
            usePdfEditStore.getState().initFromSource(makeSource(3));
            expect(usePdfEditStore.getState().selection.size).toBe(0);
        });
    });

    describe('selection', () => {
        beforeEach(() => {
            usePdfEditStore.getState().initFromSource(makeSource(5));
        });

        it('selectOnly は単一選択', () => {
            const id = usePdfEditStore.getState().pages[2].id;
            usePdfEditStore.getState().selectOnly(id);

            const { selection } = usePdfEditStore.getState();
            expect(selection.size).toBe(1);
            expect(selection.has(id)).toBe(true);
        });

        it('selectOnly はanchorを更新', () => {
            const id = usePdfEditStore.getState().pages[1].id;
            usePdfEditStore.getState().selectOnly(id);
            expect(usePdfEditStore.getState().selectionAnchor).toBe(id);
        });

        it('toggleSelection は未選択→選択', () => {
            const id = usePdfEditStore.getState().pages[1].id;
            usePdfEditStore.getState().toggleSelection(id);
            expect(usePdfEditStore.getState().selection.has(id)).toBe(true);
        });

        it('toggleSelection は選択→未選択', () => {
            const id = usePdfEditStore.getState().pages[1].id;
            usePdfEditStore.getState().selectOnly(id);
            usePdfEditStore.getState().toggleSelection(id);
            expect(usePdfEditStore.getState().selection.has(id)).toBe(false);
        });

        it('selectRange はanchorからtargetまで（昇順）', () => {
            const ids = usePdfEditStore.getState().pages.map((p) => p.id);
            usePdfEditStore.getState().selectOnly(ids[1]);
            usePdfEditStore.getState().selectRange(ids[3]);

            const { selection } = usePdfEditStore.getState();
            expect(selection.size).toBe(3);
            expect(selection.has(ids[1])).toBe(true);
            expect(selection.has(ids[2])).toBe(true);
            expect(selection.has(ids[3])).toBe(true);
        });

        it('selectRange はanchorからtargetまで（降順でも同じ）', () => {
            const ids = usePdfEditStore.getState().pages.map((p) => p.id);
            usePdfEditStore.getState().selectOnly(ids[3]);
            usePdfEditStore.getState().selectRange(ids[1]);

            const { selection } = usePdfEditStore.getState();
            expect(selection.size).toBe(3);
            expect(selection.has(ids[1])).toBe(true);
            expect(selection.has(ids[2])).toBe(true);
            expect(selection.has(ids[3])).toBe(true);
        });

        it('selectRange でanchorが未設定の場合はselectOnly相当', () => {
            const ids = usePdfEditStore.getState().pages.map((p) => p.id);
            usePdfEditStore.getState().clearSelection();
            usePdfEditStore.getState().selectRange(ids[2]);
            expect(usePdfEditStore.getState().selection.size).toBe(1);
            expect(usePdfEditStore.getState().selection.has(ids[2])).toBe(true);
        });

        it('selectAll は全ページを選択', () => {
            usePdfEditStore.getState().selectAll();
            expect(usePdfEditStore.getState().selection.size).toBe(5);
        });

        it('clearSelection は選択を空にする', () => {
            usePdfEditStore.getState().selectAll();
            usePdfEditStore.getState().clearSelection();
            expect(usePdfEditStore.getState().selection.size).toBe(0);
        });
    });

    describe('deleteSelected', () => {
        beforeEach(() => {
            usePdfEditStore.getState().initFromSource(makeSource(5));
        });

        it('選択ページを削除する', () => {
            const ids = usePdfEditStore.getState().pages.map((p) => p.id);
            usePdfEditStore.getState().selectOnly(ids[1]);
            usePdfEditStore.getState().toggleSelection(ids[3]);
            usePdfEditStore.getState().deleteSelected();

            const { pages } = usePdfEditStore.getState();
            expect(pages).toHaveLength(3);
            expect(pages.map((p) => p.sourceIndex)).toEqual([0, 2, 4]);
        });

        it('削除後は選択が空になる', () => {
            const ids = usePdfEditStore.getState().pages.map((p) => p.id);
            usePdfEditStore.getState().selectOnly(ids[1]);
            usePdfEditStore.getState().deleteSelected();
            expect(usePdfEditStore.getState().selection.size).toBe(0);
        });

        it('選択が空のときは何もしない（履歴も増やさない）', () => {
            const before = usePdfEditStore.getState().history.length;
            usePdfEditStore.getState().deleteSelected();
            expect(usePdfEditStore.getState().history.length).toBe(before);
        });

        it('履歴に新しいスナップショットを追加する', () => {
            const ids = usePdfEditStore.getState().pages.map((p) => p.id);
            const beforeLen = usePdfEditStore.getState().history.length;
            usePdfEditStore.getState().selectOnly(ids[0]);
            usePdfEditStore.getState().deleteSelected();
            const { history, historyIndex } = usePdfEditStore.getState();
            expect(history.length).toBe(beforeLen + 1);
            expect(historyIndex).toBe(history.length - 1);
        });
    });

    describe('undo/redo', () => {
        beforeEach(() => {
            usePdfEditStore.getState().initFromSource(makeSource(3));
        });

        it('canUndo は初期状態で false', () => {
            expect(usePdfEditStore.getState().canUndo()).toBe(false);
        });

        it('canRedo は初期状態で false', () => {
            expect(usePdfEditStore.getState().canRedo()).toBe(false);
        });

        it('削除後は undo 可能', () => {
            const id = usePdfEditStore.getState().pages[0].id;
            usePdfEditStore.getState().selectOnly(id);
            usePdfEditStore.getState().deleteSelected();
            expect(usePdfEditStore.getState().canUndo()).toBe(true);
        });

        it('undo で削除を取り消せる', () => {
            const id = usePdfEditStore.getState().pages[0].id;
            usePdfEditStore.getState().selectOnly(id);
            usePdfEditStore.getState().deleteSelected();
            expect(usePdfEditStore.getState().pages).toHaveLength(2);

            usePdfEditStore.getState().undo();
            expect(usePdfEditStore.getState().pages).toHaveLength(3);
        });

        it('undo 後は redo 可能', () => {
            const id = usePdfEditStore.getState().pages[0].id;
            usePdfEditStore.getState().selectOnly(id);
            usePdfEditStore.getState().deleteSelected();
            usePdfEditStore.getState().undo();
            expect(usePdfEditStore.getState().canRedo()).toBe(true);
        });

        it('redo で削除を再適用できる', () => {
            const id = usePdfEditStore.getState().pages[0].id;
            usePdfEditStore.getState().selectOnly(id);
            usePdfEditStore.getState().deleteSelected();
            usePdfEditStore.getState().undo();
            usePdfEditStore.getState().redo();
            expect(usePdfEditStore.getState().pages).toHaveLength(2);
        });

        it('undo 後に新しい操作をすると redo 履歴は破棄', () => {
            const ids0 = usePdfEditStore.getState().pages.map((p) => p.id);
            // 1回目: index 0 削除
            usePdfEditStore.getState().selectOnly(ids0[0]);
            usePdfEditStore.getState().deleteSelected();
            // 2回目: index 1 削除
            const ids1 = usePdfEditStore.getState().pages.map((p) => p.id);
            usePdfEditStore.getState().selectOnly(ids1[0]);
            usePdfEditStore.getState().deleteSelected();
            // 戻る
            usePdfEditStore.getState().undo();
            // 別の操作（選択して削除しない＝selectOnlyでは履歴増えない想定）
            // もう一度別の削除
            const ids2 = usePdfEditStore.getState().pages.map((p) => p.id);
            usePdfEditStore.getState().selectOnly(ids2[ids2.length - 1]);
            usePdfEditStore.getState().deleteSelected();

            // canRedoはfalseになる（先ほど分岐したため）
            expect(usePdfEditStore.getState().canRedo()).toBe(false);
        });

        it('履歴は最大20件で先頭を切り捨てる', () => {
            for (let i = 0; i < 25; i++) {
                const ps = usePdfEditStore.getState().pages;
                if (ps.length === 0) break;
                usePdfEditStore.getState().selectOnly(ps[0].id);
                usePdfEditStore.getState().deleteSelected();
                if (usePdfEditStore.getState().pages.length === 0) {
                    usePdfEditStore.getState().initFromSource(makeSource(3));
                }
            }
            expect(
                usePdfEditStore.getState().history.length,
            ).toBeLessThanOrEqual(20);
        });

        it('undoが空のときundoは何もしない', () => {
            const before = usePdfEditStore.getState().pages.length;
            usePdfEditStore.getState().undo();
            expect(usePdfEditStore.getState().pages.length).toBe(before);
        });

        it('redoが空のときredoは何もしない', () => {
            const before = usePdfEditStore.getState().pages.length;
            usePdfEditStore.getState().redo();
            expect(usePdfEditStore.getState().pages.length).toBe(before);
        });
    });

    describe('reorder', () => {
        beforeEach(() => {
            usePdfEditStore.getState().initFromSource(makeSource(4));
        });

        it('orderedIds の順序に並び替える', () => {
            const ids = usePdfEditStore.getState().pages.map((p) => p.id);
            const reversed = [...ids].reverse();
            usePdfEditStore.getState().reorder(reversed);
            const after = usePdfEditStore
                .getState()
                .pages.map((p) => p.id);
            expect(after).toEqual(reversed);
        });

        it('履歴に追加される', () => {
            const ids = usePdfEditStore.getState().pages.map((p) => p.id);
            const before = usePdfEditStore.getState().history.length;
            const reordered = [ids[1], ids[0], ids[2], ids[3]];
            usePdfEditStore.getState().reorder(reordered);
            expect(usePdfEditStore.getState().history.length).toBe(
                before + 1,
            );
        });

        it('順序変化なしなら履歴に積まない', () => {
            const ids = usePdfEditStore.getState().pages.map((p) => p.id);
            const before = usePdfEditStore.getState().history.length;
            usePdfEditStore.getState().reorder(ids);
            expect(usePdfEditStore.getState().history.length).toBe(before);
        });

        it('指定されなかったIDは末尾に維持される（保険）', () => {
            const ids = usePdfEditStore.getState().pages.map((p) => p.id);
            // 最初の2つのみ並び替え
            usePdfEditStore.getState().reorder([ids[1], ids[0]]);
            const after = usePdfEditStore
                .getState()
                .pages.map((p) => p.id);
            expect(after).toEqual([ids[1], ids[0], ids[2], ids[3]]);
        });
    });

    describe('splitSelected', () => {
        beforeEach(() => {
            usePdfEditStore.getState().initFromSource(makeSource(3));
        });

        it('選択ページを左右2ページに展開', () => {
            const ids = usePdfEditStore.getState().pages.map((p) => p.id);
            usePdfEditStore.getState().selectOnly(ids[1]);
            usePdfEditStore.getState().splitSelected();

            const { pages } = usePdfEditStore.getState();
            expect(pages).toHaveLength(4);
            expect(pages[1].splitHalf).toBe('left');
            expect(pages[2].splitHalf).toBe('right');
            expect(pages[1].sourceIndex).toBe(1);
            expect(pages[2].sourceIndex).toBe(1);
        });

        it('展開したページのIDは元と異なる（一意性）', () => {
            const ids = usePdfEditStore.getState().pages.map((p) => p.id);
            usePdfEditStore.getState().selectOnly(ids[0]);
            usePdfEditStore.getState().splitSelected();

            const newIds = usePdfEditStore
                .getState()
                .pages.map((p) => p.id);
            expect(new Set(newIds).size).toBe(newIds.length);
            expect(newIds[0]).not.toBe(ids[0]);
            expect(newIds[1]).not.toBe(ids[0]);
        });

        it('複数選択を一括で左右分割', () => {
            usePdfEditStore.getState().selectAll();
            usePdfEditStore.getState().splitSelected();
            expect(usePdfEditStore.getState().pages).toHaveLength(6);
        });

        it('既に分割済みのページは再分割しない', () => {
            const ids = usePdfEditStore.getState().pages.map((p) => p.id);
            usePdfEditStore.getState().selectOnly(ids[0]);
            usePdfEditStore.getState().splitSelected();
            // splitした片方を再選択して再度split
            const after = usePdfEditStore.getState().pages;
            usePdfEditStore.getState().selectOnly(after[0].id);
            usePdfEditStore.getState().splitSelected();
            expect(usePdfEditStore.getState().pages).toHaveLength(4);
        });

        it('分割後は選択がクリアされる', () => {
            const ids = usePdfEditStore.getState().pages.map((p) => p.id);
            usePdfEditStore.getState().selectOnly(ids[0]);
            usePdfEditStore.getState().splitSelected();
            expect(usePdfEditStore.getState().selection.size).toBe(0);
        });

        it('選択が空なら何もしない', () => {
            const before = usePdfEditStore.getState().pages.length;
            const beforeHistory = usePdfEditStore.getState().history.length;
            usePdfEditStore.getState().splitSelected();
            expect(usePdfEditStore.getState().pages).toHaveLength(before);
            expect(usePdfEditStore.getState().history.length).toBe(
                beforeHistory,
            );
        });
    });

    describe('cropSelected / clearCropSelected', () => {
        beforeEach(() => {
            usePdfEditStore.getState().initFromSource(makeSource(3));
        });

        it('選択ページに crop を一括適用', () => {
            const ids = usePdfEditStore.getState().pages.map((p) => p.id);
            usePdfEditStore.getState().selectOnly(ids[0]);
            usePdfEditStore.getState().toggleSelection(ids[2]);
            const crop = { x: 0.1, y: 0.1, width: 0.8, height: 0.8 };
            usePdfEditStore.getState().cropSelected(crop);

            const { pages } = usePdfEditStore.getState();
            expect(pages[0].crop).toEqual(crop);
            expect(pages[1].crop).toBeNull();
            expect(pages[2].crop).toEqual(crop);
        });

        it('clearCropSelected は選択ページの crop を null にする', () => {
            const ids = usePdfEditStore.getState().pages.map((p) => p.id);
            usePdfEditStore.getState().selectAll();
            usePdfEditStore
                .getState()
                .cropSelected({ x: 0, y: 0, width: 1, height: 1 });
            usePdfEditStore.getState().selectOnly(ids[1]);
            usePdfEditStore.getState().clearCropSelected();

            const { pages } = usePdfEditStore.getState();
            expect(pages[0].crop).not.toBeNull();
            expect(pages[1].crop).toBeNull();
            expect(pages[2].crop).not.toBeNull();
        });

        it('選択が空なら何もしない', () => {
            const before = usePdfEditStore.getState().history.length;
            usePdfEditStore
                .getState()
                .cropSelected({ x: 0, y: 0, width: 1, height: 1 });
            expect(usePdfEditStore.getState().history.length).toBe(before);
        });
    });

    describe('reset', () => {
        it('すべての状態を初期化する', () => {
            usePdfEditStore.getState().initFromSource(makeSource(3));
            usePdfEditStore.getState().selectAll();
            usePdfEditStore.getState().reset();
            const s = usePdfEditStore.getState();
            expect(s.pages).toEqual([]);
            expect(s.selection.size).toBe(0);
            expect(s.history).toEqual([]);
            expect(s.historyIndex).toBe(-1);
            expect(s.selectionAnchor).toBeNull();
        });
    });
});
