import { AlertCircle } from 'lucide-react';

interface ErrorMessageProps {
    readonly message: string | null;
}

export function ErrorMessage({ message }: ErrorMessageProps) {
    if (!message) return null;

    return (
        <div className="glass mt-4 flex items-start gap-2.5 rounded-xl border-[oklch(0.65_0.25_25/0.3)] p-4">
            <AlertCircle className="text-destructive mt-0.5 h-4 w-4 shrink-0 drop-shadow-[0_0_4px_oklch(0.65_0.25_25/0.5)]" />
            <p className="text-destructive text-[13px]">{message}</p>
        </div>
    );
}
