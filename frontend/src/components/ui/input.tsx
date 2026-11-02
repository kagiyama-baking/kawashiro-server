import * as React from 'react';

import { cn } from '@/lib/utils';

function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
    return (
        <input
            type={type}
            data-slot="input"
            className={cn(
                'file:text-ink-strong placeholder:text-ink-subtle border-input bg-secondary text-ink-strong hover:border-ink-subtle focus-visible:border-ring focus-visible:ring-ring/22 aria-invalid:border-destructive h-9 w-full min-w-0 rounded-md border px-3 py-1 text-base transition-[border-color,box-shadow] duration-250 file:inline-flex file:h-6 file:border-0 file:bg-transparent file:text-sm file:font-medium focus-visible:ring-3 focus-visible:outline-hidden disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm',
                className,
            )}
            {...props}
        />
    );
}

export { Input };
