import { expect, type Locator, type Page, test } from '@playwright/test';

const NOW = '2026-11-02T09:30:00+09:00';

const session = {
    id: 's1',
    title: '朝の挨拶の練習',
    config_name: 'friendly',
    message_count: 2,
    total_audio_bytes: 1024,
    created_at: NOW,
    updated_at: NOW,
};

const detail = {
    ...session,
    messages: [
        {
            id: 1,
            sequence: 0,
            role: 'user',
            content: 'おはようございます。',
            audio_url: null,
            audio_format: '',
            audio_size_bytes: 0,
            created_at: NOW,
        },
        {
            id: 2,
            sequence: 1,
            role: 'assistant',
            content: 'おはようございます！',
            audio_url: '/talk/sessions/s1/audio/2/',
            audio_format: 'wav',
            audio_size_bytes: 1024,
            created_at: NOW,
        },
    ],
};

/** GET 以外の API 呼び出しを記録しながらモックする。 */
async function mockApi(page: Page) {
    const mutations: string[] = [];
    await page.route('**/api/**', (route) => {
        const request = route.request();
        const type = request.resourceType();
        if (type !== 'fetch' && type !== 'xhr') return route.continue();

        const path = new URL(request.url()).pathname.replace(/^\/api\//, '');
        const method = request.method();
        if (method !== 'GET') mutations.push(`${method} ${path}`);

        if (path === 'talk/configs/') {
            return route.fulfill({
                json: {
                    configs: [
                        {
                            name: 'friendly',
                            display_name: 'フレンドリー',
                            tts_enabled: true,
                        },
                    ],
                },
            });
        }
        if (path === 'talk/sessions/' && method === 'GET') {
            return route.fulfill({
                json: {
                    count: 1,
                    next: null,
                    previous: null,
                    results: [session],
                },
            });
        }
        if (path === 'talk/sessions/' && method === 'POST') {
            return route.fulfill({
                status: 201,
                json: { ...session, id: 's2', messages: [] },
            });
        }
        if (path === 'talk/sessions/s1/') {
            return route.fulfill({ json: detail });
        }
        if (method === 'GET' && /\/audio\/\d+\/$/.test(path)) {
            return route.fulfill({
                status: 200,
                contentType: 'audio/wav',
                body: Buffer.alloc(64),
            });
        }
        if (method === 'DELETE') {
            return route.fulfill({ status: 204, body: '' });
        }
        return route.fulfill({ json: {} });
    });
    return mutations;
}

/** 同じ座標を実際のマウスで間を置いて 2 回押す（2 回目は要素の有無に関わらず押す）。 */
async function clickTwice(page: Page, target: Locator) {
    const box = await target.boundingBox();
    if (!box) throw new Error('押す対象が表示されていません');
    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await page.mouse.click(x, y);
    await page.waitForTimeout(100);
    await page.mouse.click(x, y);
    // 2 回目の処理が走る余地を残してから結果を確かめる
    await page.waitForTimeout(400);
}

test.describe('チャット画面', () => {
    let mutations: string[];

    test.beforeEach(async ({ page }) => {
        mutations = await mockApi(page);
        await page.goto('/login');
        await page.evaluate(() => {
            localStorage.setItem('auth-token', 'fake-token');
            localStorage.setItem('auth-email', 'test@example.com');
        });
    });

    test('新規チャットの作成を続けて押しても 1 件だけ作成する', async ({
        page,
    }) => {
        await page.goto('/talk');
        await page.getByRole('button', { name: '新規' }).click();
        await page.getByRole('combobox', { name: 'プリセット' }).click();
        await page.getByRole('option', { name: 'フレンドリー' }).click();

        await clickTwice(
            page,
            page.getByRole('button', { name: '作成', exact: true }),
        );

        expect(mutations).toEqual(['POST talk/sessions/']);
    });

    test('確認ダイアログの確定を続けて押しても 1 回だけ実行する', async ({
        page,
    }) => {
        await page.goto('/talk');
        await page.getByText('朝の挨拶の練習').click();
        await page.getByRole('button', { name: '音声を全削除' }).click();

        await clickTwice(page, page.getByRole('button', { name: '全て削除' }));

        expect(mutations).toEqual(['DELETE talk/sessions/s1/audio/']);
    });

    test('確認ダイアログをキャンセルすると何も実行しない', async ({ page }) => {
        await page.goto('/talk');
        await page.getByText('朝の挨拶の練習').click();
        await page.getByRole('button', { name: '音声を全削除' }).click();

        const dialog = page.getByRole('alertdialog');
        await expect(
            dialog.getByRole('button', { name: 'キャンセル' }),
        ).toBeFocused();
        await dialog.getByRole('button', { name: 'キャンセル' }).click();

        await expect(dialog).toBeHidden();
        expect(mutations).toEqual([]);
    });

    test('高さの低い画面でも入力欄までスクロールで届く', async ({ page }) => {
        await page.setViewportSize({ width: 844, height: 390 });
        await page.goto('/talk');
        await page.getByText('朝の挨拶の練習').click();

        const send = page.getByRole('button', { name: '送信' });
        await send.scrollIntoViewIfNeeded();

        await expect(send).toBeInViewport({ ratio: 1 });
    });

    test('ページに h1 が 1 つある', async ({ page }) => {
        await page.goto('/talk');
        await expect(page.locator('h1')).toHaveCount(1);
    });
});
