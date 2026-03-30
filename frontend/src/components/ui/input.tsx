import * as React from 'react';

import { cn } from '@/lib/utils';

function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
    return (
        <input
            type={type}
            data-slot="input"
            className={cn(
                'file:text-foreground placeholder:text-muted-foreground disabled:bg-input/50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 dark:disabled:bg-input/80 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 h-8 w-full min-w-0 rounded-lg border border-[oklch(0.95_0_0/0.08)] px-2.5 py-1 text-base transition-all duration-200 outline-none file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium focus-visible:border-[oklch(0.82_0.18_192/0.5)] focus-visible:shadow-[0_0_8px_oklch(0.82_0.18_192/0.12)] focus-visible:ring-3 focus-visible:ring-[oklch(0.82_0.18_192/0.15)] disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:ring-3 md:text-sm dark:bg-[oklch(0.10_0.005_240)]',
                className,
            )}
            {...props}
        />
    );
}

export { Input };
