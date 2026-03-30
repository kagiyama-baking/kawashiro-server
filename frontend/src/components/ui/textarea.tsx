import * as React from 'react';

import { cn } from '@/lib/utils';

function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
    return (
        <textarea
            data-slot="textarea"
            className={cn(
                'placeholder:text-muted-foreground disabled:bg-input/50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:disabled:bg-input/80 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 flex field-sizing-content min-h-16 w-full rounded-lg border border-[oklch(0.95_0_0/0.08)] px-2.5 py-2 text-base transition-all duration-200 outline-none focus-visible:border-[oklch(0.82_0.18_192/0.5)] focus-visible:shadow-[0_0_8px_oklch(0.82_0.18_192/0.12)] focus-visible:ring-3 focus-visible:ring-[oklch(0.82_0.18_192/0.15)] disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:ring-3 md:text-sm dark:bg-[oklch(0.10_0.005_240)]',
                className,
            )}
            {...props}
        />
    );
}

export { Textarea };
