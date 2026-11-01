import * as React from 'react';

import { cn } from '@/lib/utils';

function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
    return (
        <textarea
            data-slot="textarea"
            className={cn(
                'placeholder:text-ink-subtle border-input bg-secondary text-ink-strong hover:border-ink-subtle focus-visible:border-ring focus-visible:ring-ring/22 aria-invalid:border-destructive flex field-sizing-content min-h-16 w-full rounded-md border px-3 py-2 text-base transition-[border-color,box-shadow] duration-250 focus-visible:ring-3 focus-visible:outline-hidden disabled:cursor-not-allowed disabled:opacity-50 md:text-sm',
                className,
            )}
            {...props}
        />
    );
}

export { Textarea };
