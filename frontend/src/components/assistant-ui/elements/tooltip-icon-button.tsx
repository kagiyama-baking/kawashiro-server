import type { ComponentProps } from 'react';
import { Button } from '@/components/ui/button';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';

type TooltipIconButtonProps = ComponentProps<typeof Button> & {
    readonly tooltip: string;
    readonly side?: 'top' | 'bottom' | 'left' | 'right';
};

/** アイコンだけのボタン。ツールチップと同じ文言を読み上げ用の名前にする。 */
export function TooltipIconButton({
    children,
    tooltip,
    side = 'bottom',
    ...rest
}: TooltipIconButtonProps) {
    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger asChild>
                    <Button variant="ghost" size="icon-sm" {...rest}>
                        {children}
                        <span className="sr-only">{tooltip}</span>
                    </Button>
                </TooltipTrigger>
                <TooltipContent side={side}>{tooltip}</TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}
