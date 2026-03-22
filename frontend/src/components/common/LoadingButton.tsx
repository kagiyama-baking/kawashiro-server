import { Loader2 } from 'lucide-react';
import type { ComponentProps, ReactNode } from 'react';
import { Button } from '@/components/ui/button';

interface LoadingButtonProps extends ComponentProps<typeof Button> {
    readonly isLoading: boolean;
    readonly loadingText?: string;
    readonly children: ReactNode;
}

export function LoadingButton({
    isLoading,
    loadingText,
    children,
    disabled,
    ...props
}: LoadingButtonProps) {
    return (
        <Button disabled={isLoading || disabled} {...props}>
            {isLoading ? (
                <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    {loadingText ?? children}
                </>
            ) : (
                children
            )}
        </Button>
    );
}
