import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { Slot } from 'radix-ui';

import { cn } from '@/lib/utils';

const buttonVariants = cva(
    "group/button inline-flex shrink-0 items-center justify-center rounded-md border border-transparent font-medium tracking-[0.06em] whitespace-nowrap transition-colors select-none disabled:pointer-events-none disabled:opacity-45 aria-invalid:border-destructive [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
    {
        variants: {
            variant: {
                default:
                    'bg-primary text-primary-foreground hover:bg-primary-hover',
                outline:
                    'border-input bg-card text-ink-strong hover:border-primary hover:text-primary-hover aria-expanded:border-primary aria-expanded:text-primary-hover',
                secondary:
                    'bg-secondary text-secondary-foreground hover:text-primary-hover aria-expanded:text-primary-hover',
                ghost: 'text-muted-foreground hover:bg-accent hover:text-accent-foreground aria-expanded:bg-accent aria-expanded:text-accent-foreground',
                // 淡い地の濃さを変えると文字のコントラストが 4.5:1 を切るので、hover は枠で示す
                destructive:
                    'bg-destructive/10 text-destructive hover:border-destructive/50',
                link: 'text-primary underline-offset-4 hover:text-primary-hover hover:underline',
            },
            size: {
                default:
                    'h-9 gap-2 px-[1.15rem] text-[0.86rem] has-data-[icon=inline-end]:pr-3.5 has-data-[icon=inline-start]:pl-3.5',
                xs: "h-6 gap-1 px-2 text-xs has-data-[icon=inline-end]:pr-1.5 has-data-[icon=inline-start]:pl-1.5 [&_svg:not([class*='size-'])]:size-3",
                sm: "h-[30px] gap-1.5 px-[0.7rem] text-[0.8rem] has-data-[icon=inline-end]:pr-2 has-data-[icon=inline-start]:pl-2 [&_svg:not([class*='size-'])]:size-3.5",
                lg: 'h-10 gap-2 px-6 text-sm has-data-[icon=inline-end]:pr-5 has-data-[icon=inline-start]:pl-5',
                icon: 'size-9',
                'icon-xs': "size-6 [&_svg:not([class*='size-'])]:size-3",
                'icon-sm': 'size-[30px]',
                'icon-lg': 'size-10',
            },
        },
        defaultVariants: {
            variant: 'default',
            size: 'default',
        },
    },
);

function Button({
    className,
    variant = 'default',
    size = 'default',
    asChild = false,
    ...props
}: React.ComponentProps<'button'> &
    VariantProps<typeof buttonVariants> & {
        asChild?: boolean;
    }) {
    const Comp = asChild ? Slot.Root : 'button';

    return (
        <Comp
            data-slot="button"
            data-variant={variant}
            data-size={size}
            className={cn(buttonVariants({ variant, size, className }))}
            {...props}
        />
    );
}

export { Button, buttonVariants };
