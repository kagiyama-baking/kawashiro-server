import { AlertCircle } from 'lucide-react';

interface ErrorMessageProps {
    readonly message: string | null;
}

export function ErrorMessage({ message }: ErrorMessageProps) {
    if (!message) return null;

    return (
        <div className="border-destructive/30 bg-destructive/10 mt-4 flex items-start gap-2 rounded-lg border p-3">
            <AlertCircle className="text-destructive mt-0.5 h-4 w-4 shrink-0" />
            <p className="text-destructive text-sm">{message}</p>
        </div>
    );
}
