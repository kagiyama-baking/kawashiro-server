import { expect, test } from '@playwright/test';

test.describe('ナビゲーション', () => {
    test.beforeEach(async ({ page }) => {
        // XHR/fetchのAPIリクエストのみモック（HTMLリクエストは除外）
        await page.route('**/api/**', (route) => {
            if (route.request().resourceType() === 'fetch' || route.request().resourceType() === 'xhr') {
                return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ models: [], settings: [], styles: [] }) });
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
        const main = page.locator('main');
        await expect(main.getByText('テキスト読み上げ')).toBeVisible();
        await expect(main.getByText('チャット')).toBeVisible();
        await expect(main.getByText('メディア変換')).toBeVisible();
        await expect(main.getByText('PDF編集')).toBeVisible();
    });

    test('ホームのメニューカードから遷移できる', async ({ page }) => {
        await page.goto('/');
        await page
            .locator('main')
            .getByRole('link', { name: 'メディア変換' })
            .click();
        await expect(page).toHaveURL('/media');
    });

    test('サイドバーからテキスト読み上げに遷移できる', async ({ page }) => {
        await page.goto('/');
        await page
            .locator('aside')
            .getByRole('link', { name: 'テキスト読み上げ' })
            .click();
        await expect(page).toHaveURL('/tts');
    });

    test('サイドバーからチャットに遷移できる', async ({ page }) => {
        await page.goto('/');
        await page
            .locator('aside')
            .getByRole('link', { name: 'チャット' })
            .click();
        await expect(page).toHaveURL('/talk');
    });

    test('サイドバーからメディア変換に遷移できる', async ({ page }) => {
        await page.goto('/');
        await page
            .locator('aside')
            .getByRole('link', { name: 'メディア変換' })
            .click();
        await expect(page).toHaveURL('/media');
    });

    test('サイドバーからPDF編集に遷移できる', async ({ page }) => {
        await page.goto('/');
        await page
            .locator('aside')
            .getByRole('link', { name: 'PDF編集' })
            .click();
        await expect(page).toHaveURL('/pdf-edit');
    });

    test('サイドバーの現在地に aria-current が付く', async ({ page }) => {
        await page.goto('/tts');
        await expect(
            page
                .locator('aside')
                .getByRole('link', { name: 'テキスト読み上げ' }),
        ).toHaveAttribute('aria-current', 'page');
        await expect(
            page.locator('aside').getByRole('link', { name: 'ホーム' }),
        ).not.toHaveAttribute('aria-current');
    });

    test('サイドバーのメニューはチャットでも他のページと同じ位置と大きさで表示される', async ({
        page,
    }) => {
        const menuBoxes = async () => {
            const links = page
                .getByRole('navigation', { name: 'メインメニュー' })
                .getByRole('link');
            await expect(links).toHaveCount(5);
            await expect(links.last()).toBeVisible();
            // 描画の後で待つ。先に待つと、まだ読み込みが始まっていない書体は待てない
            await page.evaluate(async () => {
                await document.fonts.ready;
            });
            return Promise.all(
                (await links.all()).map((link) => link.boundingBox()),
            );
        };

        await page.goto('/tts');
        const onTts = await menuBoxes();
        await page.goto('/talk');
        const onTalk = await menuBoxes();

        expect(onTalk).toEqual(onTts);
    });

    test('ログアウトするとログイン画面に遷移する', async ({ page }) => {
        await page.goto('/');
        await page.getByRole('button', { name: 'ログアウト' }).click();
        await expect(page).toHaveURL('/login');
    });

    test('スマホ幅ではメニューボタンからドロワーを開いて遷移できる', async ({
        page,
    }) => {
        await page.setViewportSize({ width: 390, height: 844 });
        await page.goto('/');
        await page.getByRole('button', { name: 'メニューを開く' }).click();
        await page
            .locator('aside')
            .getByRole('link', { name: 'チャット' })
            .click();
        await expect(page).toHaveURL('/talk');
    });
});
