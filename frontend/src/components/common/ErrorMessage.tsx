import { AlertCircle } from 'lucide-react';

interface ErrorMessageProps {
    readonly message: string | null;
}

export function ErrorMessage({ message }: ErrorMessageProps) {
    if (!message) return null;

    return (
        <div
            role="alert"
            className="bg-card border-border border-l-destructive mt-4 flex items-start gap-2.5 rounded-lg border border-l-3 px-[1.1rem] py-[0.95rem]"
        >
            <AlertCircle className="text-destructive mt-1 h-4 w-4 shrink-0" />
            <p className="text-destructive min-w-0 text-sm wrap-anywhere">
                {message}
            </p>
        </div>
    );
}
