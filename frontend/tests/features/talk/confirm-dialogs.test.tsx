import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatMessageItem } from '@/features/talk/ChatMessageItem';
import { ChatPage } from '@/features/talk/ChatPage';
import { ChatThreadView } from '@/features/talk/ChatThreadView';
import { useChatStore } from '@/stores/chat-store';
import type {
    ChatSessionDetail,
    ChatSessionListItem,
    ChatSessionMessage,
} from '@/types/talk';

vi.mock('@/lib/api/talk', async (importOriginal) => ({
    ...(await importOriginal<typeof import('@/lib/api/talk')>()),
    fetchConfigs: vi.fn().mockResolvedValue([]),
}));

const NOW = '2026-11-02T09:30:00+09:00';

const audioMessage: ChatSessionMessage = {
    id: 2,
    sequence: 1,
    role: 'assistant',
    content: 'おはようございます',
    audio_url: '/talk/sessions/s1/audio/2/',
    audio_format: 'wav',
    audio_size_bytes: 1024,
    created_at: NOW,
};

const listItem: ChatSessionListItem = {
    id: 's1',
    title: '朝の挨拶の練習',
    config_name: 'friendly',
    message_count: 1,
    total_audio_bytes: 1024,
    created_at: NOW,
    updated_at: NOW,
};

const detail: ChatSessionDetail = { ...listItem, messages: [audioMessage] };

async function answer(user: ReturnType<typeof userEvent.setup>, name: string) {
    await user.click(
        within(screen.getByRole('alertdialog')).getByRole('button', { name }),
    );
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
}

// 続けて押したときの二重実行は jsdom では再現しないので、e2e/talk.spec.ts で確かめる
describe('Talk の確認ダイアログ', () => {
    const initialState = useChatStore.getState();

    beforeEach(() => {
        // jsdom には scrollIntoView がない
        Element.prototype.scrollIntoView = vi.fn();
        useChatStore.setState({
            ...initialState,
            ensureAudioObjectUrl: vi.fn().mockResolvedValue('blob:audio'),
            activeSession: detail,
            activeSessionId: detail.id,
        });
    });

    afterEach(() => {
        useChatStore.setState(initialState, true);
    });

    describe('音声 1 件の削除', () => {
        function setup() {
            const deleteMessageAudio = vi.fn().mockResolvedValue(undefined);
            useChatStore.setState({ deleteMessageAudio });
            render(
                <ChatMessageItem
                    message={audioMessage}
                    disabled={false}
                    onEdit={vi.fn()}
                />,
            );
            return { deleteMessageAudio, user: userEvent.setup() };
        }

        it('キャンセルすると削除しない', async () => {
            const { deleteMessageAudio, user } = setup();

            await user.click(
                screen.getByRole('button', { name: '音声を削除' }),
            );
            await answer(user, 'キャンセル');

            expect(deleteMessageAudio).not.toHaveBeenCalled();
        });

        it('確定すると削除する', async () => {
            const { deleteMessageAudio, user } = setup();

            await user.click(
                screen.getByRole('button', { name: '音声を削除' }),
            );
            await answer(user, '削除');

            expect(deleteMessageAudio).toHaveBeenCalledTimes(1);
            expect(deleteMessageAudio).toHaveBeenCalledWith(audioMessage.id);
        });
    });

    describe('音声の全削除', () => {
        function setup() {
            const deleteAllAudio = vi.fn().mockResolvedValue(undefined);
            useChatStore.setState({ deleteAllAudio });
            render(<ChatThreadView />);
            return { deleteAllAudio, user: userEvent.setup() };
        }

        it('キャンセルすると削除しない', async () => {
            const { deleteAllAudio, user } = setup();

            await user.click(
                screen.getByRole('button', { name: '音声を全削除' }),
            );
            await answer(user, 'キャンセル');

            expect(deleteAllAudio).not.toHaveBeenCalled();
        });

        it('確定すると削除する', async () => {
            const { deleteAllAudio, user } = setup();

            await user.click(
                screen.getByRole('button', { name: '音声を全削除' }),
            );
            await answer(user, '全て削除');

            expect(deleteAllAudio).toHaveBeenCalledTimes(1);
        });
    });

    describe('セッションの削除', () => {
        function setup() {
            const removeSession = vi.fn().mockResolvedValue(undefined);
            useChatStore.setState({
                removeSession,
                loadSessions: vi.fn().mockResolvedValue(undefined),
                reset: vi.fn(),
                sessions: [listItem],
            });
            render(<ChatPage />);
            return { removeSession, user: userEvent.setup() };
        }

        it('キャンセルすると削除しない', async () => {
            const { removeSession, user } = setup();

            await user.click(
                screen.getByRole('button', {
                    name: 'セッションを削除',
                }),
            );
            await answer(user, 'キャンセル');

            expect(removeSession).not.toHaveBeenCalled();
        });

        it('確定すると対象のセッションを削除する', async () => {
            const { removeSession, user } = setup();

            await user.click(
                screen.getByRole('button', {
                    name: 'セッションを削除',
                }),
            );
            await answer(user, '削除');

            await waitFor(() => {
                expect(removeSession).toHaveBeenCalledTimes(1);
            });
            expect(removeSession).toHaveBeenCalledWith(listItem.id);
        });
    });
});
