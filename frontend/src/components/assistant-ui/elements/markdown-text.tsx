import '@assistant-ui/react-markdown/styles/dot.css';

import {
    type CodeHeaderProps,
    MarkdownTextPrimitive,
    memoizeMarkdownComponents,
    useIsMarkdownCodeBlock,
} from '@assistant-ui/react-markdown';
import { CheckIcon, CopyIcon } from 'lucide-react';
import remarkBreaks from 'remark-breaks';
import remarkGfm from 'remark-gfm';
import { TooltipIconButton } from '@/components/assistant-ui/elements/tooltip-icon-button';
import { useCopyToClipboard } from '@/hooks/use-copy-to-clipboard';
import { cn } from '@/lib/utils';

// remark-breaks で 1 回の改行も改行として表示する（従来の whitespace-pre-wrap と同じ見え方にする）
const REMARK_PLUGINS = [remarkGfm, remarkBreaks];

const LINK_CLASS =
    'text-primary hover:text-primary-hover wrap-anywhere underline underline-offset-2 transition-colors';

function CodeHeader({ language, code }: CodeHeaderProps) {
    const { isCopied, copyToClipboard } = useCopyToClipboard();
    const label = language === 'unknown' ? '' : language;

    return (
        <div className="bg-card mt-3 flex items-center justify-between gap-2 rounded-t-lg border border-b-0 py-1 pr-1 pl-3.5 text-xs">
            <span className="font-latin text-muted-foreground lowercase">
                {label}
            </span>
            <TooltipIconButton
                tooltip="コードをコピー"
                onClick={() => {
                    if (code) copyToClipboard(code);
                }}
            >
                {isCopied ? <CheckIcon /> : <CopyIcon />}
            </TooltipIconButton>
        </div>
    );
}

const components = memoizeMarkdownComponents({
    h1: ({ className, ...props }) => (
        <h1
            className={cn(
                'mt-6 mb-2 text-xl first:mt-0 last:mb-0 sm:text-2xl',
                className,
            )}
            {...props}
        />
    ),
    h2: ({ className, ...props }) => (
        <h2
            className={cn(
                'mt-6 mb-2 text-lg first:mt-0 last:mb-0 sm:text-xl',
                className,
            )}
            {...props}
        />
    ),
    h3: ({ className, ...props }) => (
        <h3
            className={cn(
                'mt-5 mb-1.5 text-base first:mt-0 last:mb-0 sm:text-lg',
                className,
            )}
            {...props}
        />
    ),
    h4: ({ className, ...props }) => (
        <h4
            className={cn(
                'text-ink-strong mt-4 mb-1 font-semibold first:mt-0 last:mb-0',
                className,
            )}
            {...props}
        />
    ),
    h5: ({ className, ...props }) => (
        <h5
            className={cn(
                'text-ink-strong mt-3 mb-1 text-sm font-semibold first:mt-0 last:mb-0',
                className,
            )}
            {...props}
        />
    ),
    h6: ({ className, ...props }) => (
        <h6
            className={cn(
                'text-muted-foreground mt-3 mb-1 text-sm font-semibold first:mt-0 last:mb-0',
                className,
            )}
            {...props}
        />
    ),
    p: ({ className, ...props }) => (
        <p className={cn('my-3 first:mt-0 last:mb-0', className)} {...props} />
    ),
    a: ({ className, ...props }) => (
        <a
            className={cn(LINK_CLASS, className)}
            {...props}
            target="_blank"
            rel="noreferrer noopener"
        />
    ),
    // 外部の画像を自動で読み込むと、URL に載せた内容がそのサーバーへ送られてしまうので、リンクにとどめる
    img: ({ src, alt }) => (
        <a
            className={LINK_CLASS}
            href={typeof src === 'string' ? src : undefined}
            target="_blank"
            rel="noreferrer noopener"
        >
            {alt || '画像を開く'}
        </a>
    ),
    blockquote: ({ className, ...props }) => (
        <blockquote
            className={cn(
                'border-input text-muted-foreground my-3 border-s-2 ps-4',
                className,
            )}
            {...props}
        />
    ),
    ul: ({ className, ...props }) => (
        <ul
            className={cn(
                'marker:text-ink-subtle my-3 ms-5 list-disc [&>li]:mt-1',
                className,
            )}
            {...props}
        />
    ),
    ol: ({ className, ...props }) => (
        <ol
            className={cn(
                'marker:text-ink-subtle my-3 ms-5 list-decimal [&>li]:mt-1',
                className,
            )}
            {...props}
        />
    ),
    hr: ({ className, ...props }) => (
        <hr className={cn('my-5', className)} {...props} />
    ),
    table: ({ className, ...props }) => (
        <div className="my-3 overflow-x-auto">
            <table
                className={cn(
                    'w-full border-collapse text-sm [word-break:normal]',
                    className,
                )}
                {...props}
            />
        </div>
    ),
    th: ({ className, ...props }) => (
        <th
            className={cn(
                'bg-card text-ink-strong border px-3 py-1.5 text-start font-medium whitespace-nowrap [[align=center]]:text-center [[align=right]]:text-right',
                className,
            )}
            {...props}
        />
    ),
    td: ({ className, ...props }) => (
        <td
            className={cn(
                'min-w-[5em] border px-3 py-1.5 text-start [overflow-wrap:break-word] [[align=center]]:text-center [[align=right]]:text-right',
                className,
            )}
            {...props}
        />
    ),
    strong: ({ className, ...props }) => (
        <strong
            className={cn('text-ink-strong font-semibold', className)}
            {...props}
        />
    ),
    pre: ({ className, ...props }) => (
        <pre
            className={cn(
                'bg-secondary mb-3 overflow-x-auto rounded-b-lg border p-3.5 font-mono text-[0.8125rem] leading-[1.7] last:mb-0',
                className,
            )}
            {...props}
        />
    ),
    code: function Code({ className, ...props }) {
        const isCodeBlock = useIsMarkdownCodeBlock();
        return (
            <code
                className={cn(
                    !isCodeBlock &&
                        'bg-secondary rounded-md border px-1.5 py-0.5 font-mono text-[0.85em] wrap-anywhere',
                    className,
                )}
                {...props}
            />
        );
    },
    CodeHeader,
});

/** アシスタントの応答を Markdown で描画する。生の HTML は描画しない（react-markdown の既定）。 */
export function MarkdownText() {
    return (
        <MarkdownTextPrimitive
            remarkPlugins={REMARK_PLUGINS}
            className="aui-md min-w-0 wrap-anywhere"
            components={components}
            defer
        />
    );
}
