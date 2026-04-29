import * as React from 'react';
import { Checkbox as CheckboxPrimitive } from 'radix-ui';
import { Check } from 'lucide-react';

import { cn } from '@/lib/utils';

function Checkbox({
    className,
    ...props
}: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
    return (
        <CheckboxPrimitive.Root
            data-slot="checkbox"
            className={cn(
                'peer focus-visible:ring-ring shrink-0 rounded border shadow-sm transition-all duration-200 focus-visible:ring-1 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50',
                'h-4 w-4',
                'border-[oklch(0.65_0.01_240/0.5)] bg-[oklch(0.15_0_0/0.6)]',
                'data-[state=checked]:border-[oklch(0.75_0.20_155)] data-[state=checked]:bg-[oklch(0.75_0.20_155)] data-[state=checked]:text-black',
                'data-[state=checked]:shadow-[0_0_8px_oklch(0.75_0.20_155/0.5)]',
                className,
            )}
            {...props}
        >
            <CheckboxPrimitive.Indicator
                data-slot="checkbox-indicator"
                className={cn('flex items-center justify-center text-current')}
            >
                <Check className="h-3 w-3" strokeWidth={3} />
            </CheckboxPrimitive.Indicator>
        </CheckboxPrimitive.Root>
    );
}

export { Checkbox };
