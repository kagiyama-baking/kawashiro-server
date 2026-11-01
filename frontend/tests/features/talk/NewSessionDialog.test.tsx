import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { NewSessionDialog } from '@/features/talk/NewSessionDialog';
import type { GenerateConfig } from '@/types/talk';

const CONFIGS: GenerateConfig[] = [
    { name: 'friendly', display_name: 'フレンドリー', tts_enabled: true },
    { name: 'formal', display_name: 'フォーマル', tts_enabled: false },
];

function setup(configs: GenerateConfig[] = CONFIGS) {
    const onClose = vi.fn();
    const onCreate = vi.fn().mockResolvedValue(undefined);
    render(
        <NewSessionDialog
            configs={configs}
            open
            onClose={onClose}
            onCreate={onCreate}
        />,
    );
    return { onClose, onCreate, user: userEvent.setup() };
}

describe('NewSessionDialog', () => {
    it('open が false のときは何も表示しない', () => {
        render(
            <NewSessionDialog
                configs={CONFIGS}
                open={false}
                onClose={vi.fn()}
                onCreate={vi.fn()}
            />,
        );

        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('タイトルと説明で名付けられたダイアログとして表示する', () => {
        setup();

        expect(
            screen.getByRole('dialog', { name: '新しいチャット' }),
        ).toHaveAccessibleDescription(
            '使用するプリセットを選択してください。途中で変更はできません。',
        );
    });

    it('作成すると選択中のプリセットを渡して閉じる', async () => {
        const { onClose, onCreate, user } = setup();

        await user.click(screen.getByRole('button', { name: '作成' }));

        expect(onCreate).toHaveBeenCalledWith('friendly');
        await waitFor(() => {
            expect(onClose).toHaveBeenCalledTimes(1);
        });
    });

    it('プリセットが選ばれていなければ作成できない', () => {
        setup([]);

        expect(screen.getByRole('button', { name: '作成' })).toBeDisabled();
    });

    it('キャンセルすると作成せずに閉じる', async () => {
        const { onClose, onCreate, user } = setup();

        await user.click(screen.getByRole('button', { name: 'キャンセル' }));

        expect(onClose).toHaveBeenCalledTimes(1);
        expect(onCreate).not.toHaveBeenCalled();
    });

    it('Esc キーで閉じる', async () => {
        const { onClose, onCreate, user } = setup();

        await user.keyboard('{Escape}');

        expect(onClose).toHaveBeenCalledTimes(1);
        expect(onCreate).not.toHaveBeenCalled();
    });
});
