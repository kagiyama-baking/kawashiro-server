import { useEffect, useState } from 'react';

interface TerminalTextProps {
    readonly text: string;
}

export function TerminalText({ text }: TerminalTextProps) {
    const [displayed, setDisplayed] = useState('');
    const [done, setDone] = useState(false);

    useEffect(() => {
        let i = 0;
        setDisplayed('');
        setDone(false);
        const timer = setInterval(() => {
            if (i < text.length) {
                setDisplayed(text.slice(0, i + 1));
                i++;
            } else {
                setDone(true);
                clearInterval(timer);
            }
        }, 40);
        return () => clearInterval(timer);
    }, [text]);

    return (
        <p className="mt-1 font-mono text-xs text-[oklch(0.75_0.20_155)]">
            <span className="text-muted-foreground">$</span> {displayed}
            <span className={done ? 'animate-pulse' : ''}>▊</span>
        </p>
    );
}
