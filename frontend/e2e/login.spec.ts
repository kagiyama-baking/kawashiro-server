import { expect, test } from '@playwright/test';

test.describe('ログイン画面', () => {
    test('未認証でアクセスするとログイン画面にリダイレクトされる', async ({
        page,
    }) => {
        await page.goto('/tts');
        await expect(page).toHaveURL('/login');
    });

    test('ログインフォームが表示される', async ({ page }) => {
        await page.goto('/login');
        await expect(page.getByText('鍵山製パンWebApp')).toBeVisible();
        await expect(page.getByLabel('メールアドレス')).toBeVisible();
        await expect(page.getByLabel('パスワード')).toBeVisible();
        await expect(
            page.getByRole('button', { name: 'ログイン' }),
        ).toBeVisible();
    });

    test('空のフォームではログインボタンがクリックできない（HTML required）', async ({
        page,
    }) => {
        await page.goto('/login');
        const emailInput = page.getByLabel('メールアドレス');
        await expect(emailInput).toHaveAttribute('required', '');
    });
});
