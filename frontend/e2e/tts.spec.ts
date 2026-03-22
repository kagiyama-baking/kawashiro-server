import { expect, test } from '@playwright/test';

test.describe('テキスト読み上げ画面', () => {
    test.beforeEach(async ({ page }) => {
        // APIモック
        await page.route('**/api/tts/models/', (route) =>
            route.fulfill({
                status: 200,
                json: { models: ['test-model'] },
            }),
        );
        await page.route('**/api/tts/models/*/styles/', (route) =>
            route.fulfill({
                status: 200,
                json: { styles: ['Neutral', 'Happy'] },
            }),
        );
        // 認証設定
        await page.goto('/login');
        await page.evaluate(() => {
            localStorage.setItem('auth-token', 'fake-token');
            localStorage.setItem('auth-email', 'test@example.com');
        });
        await page.goto('/tts');
    });

    test('テキスト入力フォームが表示される', async ({ page }) => {
        await expect(page.getByLabel('テキスト')).toBeVisible();
        await expect(
            page.getByRole('button', { name: '音声を生成' }),
        ).toBeVisible();
    });

    test('テキストが空のとき送信ボタンが無効', async ({ page }) => {
        await expect(
            page.getByRole('button', { name: '音声を生成' }),
        ).toBeDisabled();
    });

    test('テキストを入力すると送信ボタンが有効になる', async ({ page }) => {
        await page.getByLabel('テキスト').fill('テスト');
        await expect(
            page.getByRole('button', { name: '音声を生成' }),
        ).toBeEnabled();
    });

    test('文字数カウンターが動作する', async ({ page }) => {
        await page.getByLabel('テキスト').fill('あいう');
        await expect(page.getByText('3/500文字')).toBeVisible();
    });

    test('詳細パラメータカードが表示される', async ({ page }) => {
        await expect(page.getByText('詳細パラメータ')).toBeVisible();
        await expect(page.getByText('スピード')).toBeVisible();
    });
});
