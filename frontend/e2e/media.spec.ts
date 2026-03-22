import { expect, test } from '@playwright/test';

test.describe('メディア変換画面', () => {
    test.beforeEach(async ({ page }) => {
        // XHR/fetchのAPIリクエストのみモック
        await page.route('**/api/**', (route) => {
            if (route.request().resourceType() === 'fetch' || route.request().resourceType() === 'xhr') {
                return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) });
            }
            return route.continue();
        });
        await page.goto('/login');
        await page.waitForLoadState('domcontentloaded');
        await page.evaluate(() => {
            localStorage.setItem('auth-token', 'fake-token');
            localStorage.setItem('auth-email', 'test@example.com');
        });
        await page.goto('/media');
    });

    test('タブが表示される', async ({ page }) => {
        await expect(page.getByText('画像フォーマット変換')).toBeVisible();
        await expect(page.getByText('ZIP → PDF')).toBeVisible();
    });

    test('画像フォーマット変換タブでファイル入力が表示される', async ({
        page,
    }) => {
        await expect(page.getByLabel('画像ファイル')).toBeVisible();
    });

    test('ZIP → PDFタブに切り替えできる', async ({ page }) => {
        await page.getByText('ZIP → PDF').click();
        await expect(page.getByLabel('ZIPファイル')).toBeVisible();
    });
});
