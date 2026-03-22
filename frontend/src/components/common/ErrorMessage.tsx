import { AlertCircle } from 'lucide-react';

interface ErrorMessageProps {
    readonly message: string | null;
}

export function ErrorMessage({ message }: ErrorMessageProps) {
    if (!message) return null;

    return (
        <div className="mt-4 flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <p className="text-sm text-destructive">{message}</p>
        </div>
    );
}
