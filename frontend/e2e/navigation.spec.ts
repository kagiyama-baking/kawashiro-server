import { expect, test } from '@playwright/test';

test.describe('ナビゲーション', () => {
    test.beforeEach(async ({ page }) => {
        // XHR/fetchのAPIリクエストのみモック（HTMLリクエストは除外）
        await page.route('**/api/**', (route) => {
            if (route.request().resourceType() === 'fetch' || route.request().resourceType() === 'xhr') {
                return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ models: [], configs: [], styles: [] }) });
            }
            return route.continue();
        });
        // 空ページでlocalStorageを設定
        await page.goto('/login');
        await page.evaluate(() => {
            localStorage.setItem('auth-token', 'fake-token');
            localStorage.setItem('auth-email', 'test@example.com');
        });
    });

    test('ホーム画面が表示される', async ({ page }) => {
        await page.goto('/');
        await expect(page.getByText('鍵山製パンWebApp')).toBeVisible();
    });

    test('ホームにメニューカードが表示される', async ({ page }) => {
        await page.goto('/');
        await expect(
            page.locator('main').getByText('テキスト読み上げ'),
        ).toBeVisible();
        await expect(
            page.locator('main').getByText('テキスト生成読み上げ'),
        ).toBeVisible();
        await expect(
            page.locator('main').getByText('メディア変換'),
        ).toBeVisible();
    });

    test('サイドバーからテキスト読み上げに遷移できる', async ({ page }) => {
        await page.goto('/');
        await page
            .locator('aside')
            .getByRole('link', { name: 'テキスト読み上げ' })
            .click();
        await expect(page).toHaveURL('/tts');
    });

    test('サイドバーからテキスト生成読み上げに遷移できる', async ({ page }) => {
        await page.goto('/');
        await page
            .locator('aside')
            .getByRole('link', { name: 'テキスト生成読み上げ' })
            .click();
        await expect(page).toHaveURL('/generate');
    });

    test('サイドバーからメディア変換に遷移できる', async ({ page }) => {
        await page.goto('/');
        await page
            .locator('aside')
            .getByRole('link', { name: 'メディア変換' })
            .click();
        await expect(page).toHaveURL('/media');
    });

    test('ログアウトするとログイン画面に遷移する', async ({ page }) => {
        await page.goto('/');
        await page.getByRole('button', { name: 'ログアウト' }).click();
        await expect(page).toHaveURL('/login');
    });
});
