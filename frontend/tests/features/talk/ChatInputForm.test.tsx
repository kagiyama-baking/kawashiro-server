import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ChatInputForm } from '@/features/talk/ChatInputForm';

describe('ChatInputForm', () => {
    it('isLoading=false のときは送信ボタンが表示される', () => {
        render(
            <ChatInputForm
                input="hi"
                onInputChange={() => {}}
                onSubmit={() => {}}
                onCancel={() => {}}
                isLoading={false}
            />,
        );
        expect(
            screen.getByRole('button', { name: /送信/ }),
        ).toBeInTheDocument();
        expect(
            screen.queryByRole('button', { name: /停止|キャンセル/ }),
        ).not.toBeInTheDocument();
    });

    it('isLoading=true のときは停止ボタンが表示される', () => {
        render(
            <ChatInputForm
                input="hi"
                onInputChange={() => {}}
                onSubmit={() => {}}
                onCancel={() => {}}
                isLoading={true}
            />,
        );
        expect(
            screen.getByRole('button', { name: /停止/ }),
        ).toBeInTheDocument();
    });

    it('停止ボタン押下で onCancel が呼ばれる', async () => {
        const onCancel = vi.fn();
        const onSubmit = vi.fn();
        const user = userEvent.setup();
        render(
            <ChatInputForm
                input="hi"
                onInputChange={() => {}}
                onSubmit={onSubmit}
                onCancel={onCancel}
                isLoading={true}
            />,
        );
        await user.click(screen.getByRole('button', { name: /停止/ }));
        expect(onCancel).toHaveBeenCalledTimes(1);
        expect(onSubmit).not.toHaveBeenCalled();
    });
});
