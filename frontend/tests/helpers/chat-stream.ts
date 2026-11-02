import type { ChatStreamEvent } from '@/types/talk';

export interface ControlledStream {
    readonly push: (...events: readonly ChatStreamEvent[]) => void;
    readonly end: () => void;
    readonly fail: (error: unknown) => void;
    readonly generator: (
        signal?: AbortSignal,
    ) => AsyncGenerator<ChatStreamEvent>;
    readonly isClosed: () => boolean;
}

/** 実際の fetch と同じく、中断されると読み取りが失敗するストリーム。 */
export function controlledStream(): ControlledStream {
    const queue: ChatStreamEvent[] = [];
    let wake: (() => void) | null = null;
    let ended = false;
    let failure: { readonly error: unknown } | null = null;
    let closed = false;

    const notify = () => {
        wake?.();
        wake = null;
    };

    return {
        push: (...events) => {
            queue.push(...events);
            notify();
        },
        end: () => {
            ended = true;
            notify();
        },
        fail: (error) => {
            failure = { error };
            notify();
        },
        isClosed: () => closed,
        generator: async function* (signal) {
            signal?.addEventListener('abort', () => {
                failure = { error: signal.reason };
                notify();
            });
            try {
                for (;;) {
                    if (failure) throw failure.error;
                    const next = queue.shift();
                    if (next) {
                        yield next;
                    } else if (ended) {
                        return;
                    } else {
                        await new Promise<void>((resolve) => {
                            wake = resolve;
                        });
                    }
                }
            } finally {
                closed = true;
            }
        },
    };
}
