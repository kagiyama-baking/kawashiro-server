import { useEffect, useRef, useState } from 'react';

interface UseCopyToClipboardOptions {
    readonly copiedDuration?: number;
}

/** assistant-ui のレジストリ（use-copy-to-clipboard）から取得したフック。 */
export function useCopyToClipboard({
    copiedDuration = 3000,
}: UseCopyToClipboardOptions = {}) {
    const [isCopied, setIsCopied] = useState(false);
    const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(
        undefined,
    );

    useEffect(() => () => clearTimeout(timerRef.current), []);

    const copyToClipboard = (value: string) => {
        if (!value || !navigator.clipboard) return;
        navigator.clipboard.writeText(value).then(
            () => {
                clearTimeout(timerRef.current);
                setIsCopied(true);
                timerRef.current = setTimeout(() => {
                    setIsCopied(false);
                }, copiedDuration);
            },
            () => {},
        );
    };

    return { isCopied, copyToClipboard };
}
