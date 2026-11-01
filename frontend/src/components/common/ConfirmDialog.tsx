import { type ReactNode, useRef } from 'react';
import { Button } from '@/components/ui/button';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';

interface ConfirmDialogProps {
    readonly open: boolean;
    readonly title: string;
    readonly confirmLabel: string;
    readonly destructive?: boolean;
    readonly onConfirm: () => void;
    readonly onCancel: () => void;
    /** 確認の内容。ダイアログの説明として読み上げられる。 */
    readonly children: ReactNode;
}

/**
 * ネイティブの confirm に代わる確認ダイアログ。
 *
 * 安全側（キャンセル）にフォーカスを置いて開き、明示的な選択を求めるので外を押しても閉じない。
 * 閉じるのは呼び出し側の責任で、確定なら onConfirm、取消と Esc なら onCancel が呼ばれる。
 */
export function ConfirmDialog({
    open,
    title,
    confirmLabel,
    destructive = false,
    onConfirm,
    onCancel,
    children,
}: ConfirmDialogProps) {
    const cancelRef = useRef<HTMLButtonElement>(null);
    const openerRef = useRef<HTMLElement | null>(null);

    return (
        <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
            <DialogContent
                role="alertdialog"
                showCloseButton={false}
                onOpenAutoFocus={(e) => {
                    e.preventDefault();
                    openerRef.current =
                        document.activeElement instanceof HTMLElement
                            ? document.activeElement
                            : null;
                    cancelRef.current?.focus();
                }}
                onCloseAutoFocus={(e) => {
                    // Radix の既定は Trigger へ戻すだけで、Trigger のない使い方では行き先を失う
                    e.preventDefault();
                    openerRef.current?.focus();
                }}
                onInteractOutside={(e) => e.preventDefault()}
            >
                <DialogHeader>
                    <DialogTitle>{title}</DialogTitle>
                    <DialogDescription>{children}</DialogDescription>
                </DialogHeader>
                <DialogFooter>
                    <Button
                        ref={cancelRef}
                        type="button"
                        variant="outline"
                        onClick={onCancel}
                    >
                        キャンセル
                    </Button>
                    <Button
                        type="button"
                        variant={destructive ? 'destructive' : 'default'}
                        onClick={onConfirm}
                    >
                        {confirmLabel}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
