import { expect, type Locator, type Page, test } from '@playwright/test';

const NOW = '2026-11-02T09:30:00+09:00';
const LATER = '2026-11-02T09:31:00+09:00';

interface ServerMessage {
    readonly id: number;
    readonly sequence: number;
    readonly role: 'user' | 'assistant';
    readonly content: string;
    readonly audio_url: string | null;
    readonly audio_format: string;
    readonly audio_size_bytes: number;
    readonly created_at: string;
}

interface ServerSession {
    readonly id: string;
    readonly title: string;
    readonly config_name: string;
    readonly messages: readonly ServerMessage[];
}

function message(
    id: number,
    sequence: number,
    role: 'user' | 'assistant',
    content: string,
    extra: Partial<ServerMessage> = {},
): ServerMessage {
    return {
        id,
        sequence,
        role,
        content,
        audio_url: null,
        audio_format: '',
        audio_size_bytes: 0,
        created_at: NOW,
        ...extra,
    };
}

function history(count: number): readonly ServerMessage[] {
    return Array.from({ length: count }, (_, i) =>
        message(
            100 + i,
            i,
            i % 2 === 0 ? 'user' : 'assistant',
            i % 2 === 0 ? `質問 ${i}` : `回答 ${i}`,
        ),
    );
}

const greeting: ServerSession = {
    id: 's1',
    title: '朝の挨拶の練習',
    config_name: 'friendly',
    messages: [
        message(1, 0, 'user', 'おはようございます。'),
        message(2, 1, 'assistant', 'おはようございます！', {
            audio_url: '/talk/sessions/s1/audio/2/',
            audio_format: 'wav',
            audio_size_bytes: 1024,
        }),
    ],
};

const plain: ServerSession = {
    id: 's2',
    title: '音声なしの話',
    config_name: 'plain',
    messages: [
        message(11, 0, 'user', '元の発話'),
        message(12, 1, 'assistant', '元の応答'),
    ],
};

function listItem(session: ServerSession) {
    return {
        id: session.id,
        title: session.title,
        config_name: session.config_name,
        message_count: session.messages.length,
        total_audio_bytes: session.messages.reduce(
            (sum, m) => sum + m.audio_size_bytes,
            0,
        ),
        created_at: NOW,
        updated_at: NOW,
    };
}

/** テストの中のサーバー。GET の応答はここの内容を返す。 */
interface FakeServer {
    readonly sessions: Map<string, ServerSession>;
    readonly mutations: string[];
}

/**
 * API をモックする。`route.fulfill` の本文は一括送信のみで増分を表せないので、
 * メッセージの送信と編集だけ `fetch` を差し替え、テストから 1 イベントずつ流す。
 */
async function mockApi(
    page: Page,
    sessions: readonly ServerSession[] = [greeting, plain],
): Promise<FakeServer> {
    const server: FakeServer = {
        sessions: new Map(sessions.map((s) => [s.id, s])),
        mutations: [],
    };

    await page.addInitScript(() => {
        const realFetch = window.fetch.bind(window);
        const encoder = new TextEncoder();
        const scope = window as unknown as Record<string, unknown>;
        const turns: unknown[] = [];
        scope.__turns = turns;
        scope.__failNext = null;

        window.fetch = async (input, init) => {
            const request =
                input instanceof Request ? input : new Request(input, init);
            const { pathname } = new URL(request.url);
            if (!/\/api\/talk\/sessions\/[^/]+\/messages\//.test(pathname)) {
                return realFetch(input, init);
            }

            const body = await request.clone().json();
            const failure = scope.__failNext as {
                status: number;
                body: unknown;
            } | null;
            scope.__failNext = null;
            turns.push({
                method: request.method,
                pathname,
                body,
                aborted: false,
            });
            if (failure) {
                return new Response(JSON.stringify(failure.body), {
                    status: failure.status,
                    headers: { 'Content-Type': 'application/json' },
                });
            }

            const turn = turns[turns.length - 1] as Record<string, unknown>;
            const stream = new ReadableStream<Uint8Array>({
                start(controller) {
                    turn.push = (event: string, data: unknown) => {
                        controller.enqueue(
                            encoder.encode(
                                `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`,
                            ),
                        );
                    };
                    turn.close = () => controller.close();
                    // ブラウザの fetch と同じく、中断されたら本文の読み取りを失敗させる
                    request.signal.addEventListener('abort', () => {
                        turn.aborted = true;
                        controller.error(request.signal.reason);
                    });
                },
            });
            return new Response(stream, {
                status: 200,
                headers: { 'Content-Type': 'text/event-stream' },
            });
        };
    });

    await page.route('**/api/**', (route) => {
        const request = route.request();
        const type = request.resourceType();
        if (type !== 'fetch' && type !== 'xhr') return route.continue();

        const path = new URL(request.url()).pathname.replace(/^\/api\//, '');
        const method = request.method();
        if (method !== 'GET') server.mutations.push(`${method} ${path}`);

        if (path === 'talk/configs/') {
            return route.fulfill({
                json: {
                    configs: [
                        {
                            name: 'friendly',
                            display_name: 'フレンドリー',
                            tts_enabled: true,
                        },
                        {
                            name: 'plain',
                            display_name: '音声なし',
                            tts_enabled: false,
                        },
                    ],
                },
            });
        }
        if (path === 'talk/sessions/' && method === 'GET') {
            const results = [...server.sessions.values()].map(listItem);
            return route.fulfill({
                json: {
                    count: results.length,
                    next: null,
                    previous: null,
                    results,
                },
            });
        }
        if (path === 'talk/sessions/' && method === 'POST') {
            const body = request.postDataJSON() as { config_name: string };
            const created: ServerSession = {
                id: 'new',
                title: '',
                config_name: body.config_name,
                messages: [],
            };
            server.sessions.set(created.id, created);
            return route.fulfill({
                status: 201,
                json: { ...listItem(created), messages: [] },
            });
        }

        const detail = /^talk\/sessions\/([^/]+)\/$/.exec(path);
        if (detail) {
            const session = server.sessions.get(detail[1]);
            if (method === 'DELETE') {
                server.sessions.delete(detail[1]);
                return route.fulfill({ status: 204, body: '' });
            }
            if (!session) return route.fulfill({ status: 404, json: {} });
            if (method === 'PATCH') {
                const body = request.postDataJSON() as { title: string };
                const updated = { ...session, title: body.title };
                server.sessions.set(session.id, updated);
                return route.fulfill({
                    json: { ...listItem(updated), messages: updated.messages },
                });
            }
            return route.fulfill({
                json: { ...listItem(session), messages: session.messages },
            });
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
    return server;
}

/** index 番目の送信へ SSE のイベントを流す。 */
async function pushEvent(
    page: Page,
    index: number,
    event: string,
    data: unknown = {},
) {
    await page.waitForFunction((i) => {
        const turns = (window as unknown as { __turns: { push?: unknown }[] })
            .__turns;
        return typeof turns[i]?.push === 'function';
    }, index);
    await page.evaluate(
        ([i, name, payload]) => {
            const turns = (
                window as unknown as {
                    __turns: {
                        push: (event: unknown, data: unknown) => void;
                    }[];
                }
            ).__turns;
            turns[i as number].push(name, payload);
        },
        [index, event, data] as const,
    );
}

async function turnsOf(page: Page) {
    return page.evaluate(() => {
        const turns = (
            window as unknown as {
                __turns: {
                    method: string;
                    pathname: string;
                    body: { content: string };
                    aborted: boolean;
                }[];
            }
        ).__turns;
        return turns.map(({ method, pathname, body, aborted }) => ({
            method,
            pathname,
            content: body.content,
            aborted,
        }));
    });
}

async function failNextTurn(page: Page, status: number, body: unknown) {
    await page.evaluate(
        ([s, b]) => {
            (window as unknown as { __failNext: unknown }).__failNext = {
                status: s,
                body: b,
            };
        },
        [status, body] as const,
    );
}

const composer = (page: Page) =>
    page.getByRole('textbox', { name: 'メッセージ', exact: true });
const sendButton = (page: Page) =>
    page.getByRole('button', { name: '送信', exact: true });
const stopButton = (page: Page) =>
    page.getByRole('button', { name: '停止', exact: true });
const mainArea = (page: Page) => page.locator('main');

async function sendText(page: Page, text: string) {
    await composer(page).fill(text);
    await composer(page).press('Enter');
}

/** 新規チャットを開く。プリセットが読み込まれるまで送信できないので待つ。 */
async function openNewChat(page: Page) {
    await page.goto('/talk');
    await expect(page.getByRole('combobox', { name: 'プリセット' })).toHaveText(
        'フレンドリー',
    );
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
    let server: FakeServer;

    test.beforeEach(async ({ page }) => {
        server = await mockApi(page);
        await page.goto('/login');
        await page.evaluate(() => {
            localStorage.setItem('auth-token', 'fake-token');
            localStorage.setItem('auth-email', 'test@example.com');
        });
    });

    test.describe('新規チャット', () => {
        test('プリセットを選んで送るとセッションを作り、URL を変えても画面を作り直さない', async ({
            page,
        }) => {
            await page.goto('/talk');
            await expect(mainArea(page).getByText('TALK')).toBeVisible();
            await page.getByRole('combobox', { name: 'プリセット' }).click();
            await page.getByRole('option', { name: '音声なし' }).click();
            await composer(page).evaluate((el) => {
                el.dataset.marker = 'same-element';
            });

            await sendText(page, 'こんにちは');

            await expect(page).toHaveURL('/talk/new');
            expect(server.mutations).toEqual(['POST talk/sessions/']);
            await expect(mainArea(page).getByText('こんにちは')).toBeVisible();
            await expect(composer(page)).toHaveAttribute(
                'data-marker',
                'same-element',
            );
            await expect(composer(page)).toHaveValue('');
            expect(server.sessions.get('new')?.config_name).toBe('plain');
        });

        test('応答が終わるとタイトルが一覧とヘッダに出る', async ({ page }) => {
            await openNewChat(page);
            await sendText(page, 'こんにちは');
            await pushEvent(page, 0, 'start');
            await pushEvent(page, 0, 'delta', { text: 'こんにちは！' });
            await pushEvent(page, 0, 'message', {
                user: message(5, 0, 'user', 'こんにちは'),
                assistant: message(6, 1, 'assistant', 'こんにちは！'),
            });
            await pushEvent(page, 0, 'title', { title: '最初の挨拶' });
            await pushEvent(page, 0, 'done', {
                title: '最初の挨拶',
                message_count: 2,
                total_audio_bytes: 0,
                updated_at: LATER,
            });

            await expect(
                mainArea(page).getByRole('heading', { name: '最初の挨拶' }),
            ).toBeVisible();
            await expect(
                page.getByRole('link', { name: /最初の挨拶.*2 件/ }),
            ).toHaveAttribute('aria-current', 'page');
        });

        test('最初の応答に失敗すると空のセッションを消して /talk へ戻り、本文を入力欄へ戻す', async ({
            page,
        }) => {
            await openNewChat(page);

            await sendText(page, '失敗する発話');
            await expect(page).toHaveURL('/talk/new');
            await pushEvent(page, 0, 'start');
            await pushEvent(page, 0, 'error', {
                status: 502,
                error: 'LLM に接続できません',
            });

            await expect(page).toHaveURL('/talk');
            await expect(page.getByRole('alert')).toHaveText(
                'LLM に接続できません',
            );
            await expect(composer(page)).toHaveValue('失敗する発話');
            await expect(mainArea(page).getByText('TALK')).toBeVisible();
            await expect
                .poll(() => server.mutations)
                .toEqual(['POST talk/sessions/', 'DELETE talk/sessions/new/']);
            await expect(
                page.getByRole('link', { name: /（無題）/ }),
            ).toHaveCount(0);
        });

        test('新しいチャットのリンクで /talk へ移ると表示と入力を空にする', async ({
            page,
        }) => {
            await page.goto('/talk/s2');
            await composer(page).fill('下書き');

            await page.getByRole('link', { name: '新しいチャット' }).click();

            await expect(page).toHaveURL('/talk');
            await expect(mainArea(page).getByText('TALK')).toBeVisible();
            await expect(composer(page)).toHaveValue('');
        });
    });

    test.describe('逐次表示', () => {
        test('発話をすぐ出し、応答を少しずつ出し、保存で停止ボタンを戻す', async ({
            page,
        }) => {
            await page.goto('/talk/s2');
            await expect(mainArea(page).getByText('元の応答')).toBeVisible();

            await sendText(page, '続きの発話');

            await expect(mainArea(page).getByText('続きの発話')).toBeVisible();
            await expect(page.getByText('考えています…')).toBeVisible();
            await expect(stopButton(page)).toBeVisible();
            await expect(sendButton(page)).toHaveCount(0);

            await pushEvent(page, 0, 'start');
            await pushEvent(page, 0, 'delta', { text: '少しずつ' });
            await expect(mainArea(page).getByText('少しずつ')).toBeVisible();
            await expect(page.getByText('考えています…')).toHaveCount(0);
            await expect(stopButton(page)).toBeVisible();

            await pushEvent(page, 0, 'delta', { text: '届きます' });
            await expect(
                mainArea(page).getByText('少しずつ届きます'),
            ).toBeVisible();

            await pushEvent(page, 0, 'message', {
                user: message(13, 2, 'user', '続きの発話'),
                assistant: message(14, 3, 'assistant', '少しずつ届きます'),
            });

            await expect(stopButton(page)).toHaveCount(0);
            await expect(sendButton(page)).toBeVisible();
        });

        test('保存の通知で行を作り直さない', async ({ page }) => {
            await page.goto('/talk/s2');
            await sendText(page, '続きの発話');
            await pushEvent(page, 0, 'delta', { text: '応答の本文' });
            const reply = mainArea(page).getByText('応答の本文');
            await expect(reply).toBeVisible();
            await reply.evaluate((el) => {
                el.dataset.marker = 'same-element';
            });

            await pushEvent(page, 0, 'message', {
                user: message(13, 2, 'user', '続きの発話'),
                assistant: message(14, 3, 'assistant', '応答の本文'),
            });

            await expect(stopButton(page)).toHaveCount(0);
            await expect(reply).toHaveAttribute('data-marker', 'same-element');
        });

        test('下端を追従し、上へ戻すと「いちばん下へ」のボタンが出る', async ({
            page,
        }) => {
            await page.setViewportSize({ width: 1280, height: 500 });
            await page.goto('/talk/s2');
            await sendText(page, '長い応答をください');
            const longText = Array.from(
                { length: 40 },
                (_, i) => `${i + 1} 行目の本文です。`,
            ).join('\n\n');
            await pushEvent(page, 0, 'delta', { text: longText });
            const lastLine = mainArea(page).getByText('40 行目の本文です。');

            await expect(lastLine).toBeInViewport();

            const jump = page.getByRole('button', { name: 'いちばん下へ' });
            const viewport = mainArea(page).locator(
                '[data-aui-thread-root] > .overflow-y-auto',
            );
            await viewport.evaluate((el) => {
                el.scrollTop = 0;
            });
            await expect(jump).toBeEnabled();
            await expect(lastLine).not.toBeInViewport();

            await jump.click();

            await expect(lastLine).toBeInViewport();
        });

        test('生成中に別のチャットへ移ると読み取りを中断し、遅れた応答で上書きしない', async ({
            page,
        }) => {
            await page.goto('/talk/s2');
            await sendText(page, '切り替える発話');
            await pushEvent(page, 0, 'delta', { text: '途中の応答' });
            await expect(mainArea(page).getByText('途中の応答')).toBeVisible();

            await page.getByRole('link', { name: /朝の挨拶の練習/ }).click();

            await expect(page).toHaveURL('/talk/s1');
            await expect(
                mainArea(page).getByText('おはようございます！'),
            ).toBeVisible();
            await expect(mainArea(page).getByText('途中の応答')).toHaveCount(0);
            await expect(stopButton(page)).toHaveCount(0);
            await expect
                .poll(async () => (await turnsOf(page))[0].aborted)
                .toBe(true);
        });
    });

    test.describe('停止', () => {
        test('発話と途中の応答を残し、サーバーの保存を確かめるまで送信を止める', async ({
            page,
        }) => {
            await page.goto('/talk/s2');
            await sendText(page, '止める発話');
            await pushEvent(page, 0, 'start');
            await pushEvent(page, 0, 'delta', { text: '途中まで' });
            await expect(mainArea(page).getByText('途中まで')).toBeVisible();

            await stopButton(page).click();

            await expect
                .poll(async () => (await turnsOf(page))[0].aborted)
                .toBe(true);
            await expect(page.getByText('確認しています')).toBeVisible();
            await expect(mainArea(page).getByText('止める発話')).toBeVisible();
            await expect(mainArea(page).getByText('途中まで')).toBeVisible();
            await expect(page.getByText('ここで停止しました')).toBeVisible();
            await expect(composer(page)).toHaveValue('');
            await composer(page).fill('次の発話');
            await expect(sendButton(page)).toBeDisabled();

            // サーバーの保存が確認できたら解除する
            server.sessions.set('s2', {
                ...plain,
                messages: [
                    ...plain.messages,
                    message(13, 2, 'user', '止める発話'),
                    message(14, 3, 'assistant', '途中まで保存'),
                ],
            });

            await expect(page.getByText('確認しています')).toHaveCount(0);
            await expect(
                mainArea(page).getByText('途中まで保存'),
            ).toBeVisible();
            await expect(sendButton(page)).toBeEnabled();
            await expect(page.getByRole('alert')).toHaveCount(0);
            await expect(composer(page)).toHaveValue('次の発話');

            // 同期で付いたサーバー id で編集できる
            await page
                .getByRole('button', { name: '編集', exact: true })
                .last()
                .click();
            await page
                .getByRole('textbox', { name: 'メッセージを編集' })
                .fill('直した発話');
            await page
                .getByRole('button', { name: '送信して置き換える' })
                .click();
            await expect
                .poll(async () => (await turnsOf(page))[1]?.pathname)
                .toBe('/api/talk/sessions/s2/messages/13/');
        });

        test('応答の前に停止しても発話を残す', async ({ page }) => {
            await page.goto('/talk/s2');
            await sendText(page, '止める発話');
            await expect(stopButton(page)).toBeVisible();

            await stopButton(page).click();

            await expect(mainArea(page).getByText('止める発話')).toBeVisible();
            await expect(page.getByText('考えています…')).toHaveCount(0);
            await expect(composer(page)).toHaveValue('');
            await expect(page.getByText('確認しています')).toBeVisible();
        });

        test('終端イベントなしで切れてもサーバーの値に揃える', async ({
            page,
        }) => {
            await page.goto('/talk/s2');
            await sendText(page, '切れる発話');
            await pushEvent(page, 0, 'delta', { text: '途中' });
            await expect(mainArea(page).getByText('途中')).toBeVisible();
            server.sessions.set('s2', {
                ...plain,
                messages: [
                    ...plain.messages,
                    message(13, 2, 'user', '切れる発話'),
                    message(14, 3, 'assistant', '途中まで保存'),
                ],
            });

            await page.evaluate(() => {
                (
                    window as unknown as { __turns: { close: () => void }[] }
                ).__turns[0].close();
            });

            await expect(
                mainArea(page).getByText('途中まで保存'),
            ).toBeVisible();
            await expect(sendButton(page)).toBeVisible();
        });
    });

    test.describe('編集', () => {
        const openEditor = async (page: Page) => {
            await page.goto('/talk/s2');
            await page
                .getByRole('button', { name: '編集', exact: true })
                .click({ force: true });
            return page.getByRole('textbox', { name: 'メッセージを編集' });
        };

        test('編集して送ると対象以降を置き換える', async ({ page }) => {
            const editor = await openEditor(page);
            await expect(editor).toHaveValue('元の発話');

            await editor.fill('直した発話');
            await page
                .getByRole('button', { name: '送信して置き換える' })
                .click();

            await expect(mainArea(page).getByText('直した発話')).toBeVisible();
            await expect(mainArea(page).getByText('元の応答')).toHaveCount(0);

            await pushEvent(page, 0, 'delta', { text: '新しい応答' });
            const [turn] = await turnsOf(page);
            expect(turn.method).toBe('PATCH');
            expect(turn.pathname).toBe('/api/talk/sessions/s2/messages/11/');
            expect(turn.content).toBe('直した発話');
            await pushEvent(page, 0, 'message', {
                user: message(21, 0, 'user', '直した発話'),
                assistant: message(22, 1, 'assistant', '新しい応答'),
            });
            await expect(mainArea(page).getByText('新しい応答')).toBeVisible();
            await expect(stopButton(page)).toHaveCount(0);
        });

        test('失敗すると元の履歴へ戻し、編集欄を入力文ごと開き直す', async ({
            page,
        }) => {
            const editor = await openEditor(page);
            await editor.fill('直した発話');
            await page
                .getByRole('button', { name: '送信して置き換える' })
                .click();
            await pushEvent(page, 0, 'error', {
                status: 502,
                error: '再生成に失敗しました',
            });

            await expect(page.getByRole('alert')).toHaveText(
                '再生成に失敗しました',
            );
            await expect(
                page.getByRole('textbox', { name: 'メッセージを編集' }),
            ).toHaveValue('直した発話');
            await expect(mainArea(page).getByText('元の応答')).toBeVisible();

            await page.getByRole('button', { name: 'キャンセル' }).click();
            await expect(mainArea(page).getByText('元の発話')).toBeVisible();
        });

        test('本文を変えなければ送信できない', async ({ page }) => {
            await openEditor(page);

            await expect(
                page.getByRole('button', { name: '送信して置き換える' }),
            ).toBeDisabled();
        });
    });

    test.describe('再生成', () => {
        test('同じ本文で送り直し、古い応答を置き換える', async ({ page }) => {
            await page.goto('/talk/s2');

            await page.getByRole('button', { name: '再生成' }).click();

            await expect(mainArea(page).getByText('元の応答')).toHaveCount(0);
            await pushEvent(page, 0, 'delta', { text: '別の応答' });
            await pushEvent(page, 0, 'message', {
                user: message(21, 0, 'user', '元の発話'),
                assistant: message(22, 1, 'assistant', '別の応答'),
            });
            await expect(mainArea(page).getByText('別の応答')).toBeVisible();
            const [turn] = await turnsOf(page);
            expect(turn.method).toBe('PATCH');
            expect(turn.pathname).toBe('/api/talk/sessions/s2/messages/11/');
            expect(turn.content).toBe('元の発話');
        });

        test('失敗するとバナーを出して元の応答へ戻す', async ({ page }) => {
            await page.goto('/talk/s2');

            await page.getByRole('button', { name: '再生成' }).click();
            await pushEvent(page, 0, 'error', {
                status: 504,
                error: 'タイムアウトしました',
            });

            await expect(page.getByRole('alert')).toHaveText(
                'タイムアウトしました',
            );
            await expect(mainArea(page).getByText('元の応答')).toBeVisible();
            await expect(composer(page)).toHaveValue('');
        });
    });

    test.describe('失敗時の本文復元', () => {
        test('error イベントなら発話を取り消して本文を入力欄へ戻す', async ({
            page,
        }) => {
            await page.goto('/talk/s2');
            await sendText(page, '戻るはずの本文');
            await pushEvent(page, 0, 'start');
            await pushEvent(page, 0, 'error', {
                status: 502,
                error: 'LLM に接続できません',
            });

            await expect(page.getByRole('alert')).toHaveText(
                'LLM に接続できません',
            );
            await expect(composer(page)).toHaveValue('戻るはずの本文');
            await expect(
                mainArea(page).locator('[data-message-id]', {
                    hasText: '戻るはずの本文',
                }),
            ).toHaveCount(0);
            await expect(sendButton(page)).toBeEnabled();
        });

        test('HTTP エラーならサーバーの文言を出して本文を入力欄へ戻す', async ({
            page,
        }) => {
            await page.goto('/talk/s2');
            await failNextTurn(page, 429, { detail: '少し待ってください' });

            await sendText(page, '戻るはずの本文');

            await expect(page.getByRole('alert')).toHaveText(
                '少し待ってください',
            );
            await expect(composer(page)).toHaveValue('戻るはずの本文');
        });

        test('バナーは閉じられ、次の送信でも消える', async ({ page }) => {
            await page.goto('/talk/s2');
            await failNextTurn(page, 503, { error: '混み合っています' });
            await sendText(page, '本文');
            await expect(page.getByRole('alert')).toBeVisible();

            await page
                .getByRole('button', { name: 'メッセージを閉じる' })
                .click();

            await expect(page.getByRole('alert')).toHaveCount(0);
        });
    });

    test.describe('50 件上限', () => {
        test('50 件に達したチャットでは送信を止め、新しいチャットへの導線を出す', async ({
            page,
        }) => {
            server.sessions.set('full', {
                id: 'full',
                title: '上限のチャット',
                config_name: 'plain',
                messages: history(50),
            });
            await page.goto('/talk/full');
            await expect(
                mainArea(page).getByText('回答 49', { exact: true }),
            ).toBeVisible();

            await expect(page.getByRole('status')).toContainText('上限');
            await composer(page).fill('もう送れないはず');
            await expect(sendButton(page)).toBeDisabled();
            await composer(page).press('Enter');
            expect(await turnsOf(page)).toEqual([]);
            await expect(composer(page)).toHaveValue('もう送れないはず');

            await page
                .getByRole('status')
                .getByRole('link', { name: '新しいチャット' })
                .click();

            await expect(page).toHaveURL('/talk');
            await expect(mainArea(page).getByText('TALK')).toBeVisible();
        });

        test('送信の競合で 400 が返ったらサーバーの文言を出し、本文を戻して上限の案内を出す', async ({
            page,
        }) => {
            server.sessions.set('almost', {
                id: 'almost',
                title: '上限の手前のチャット',
                config_name: 'plain',
                messages: history(48),
            });
            await page.goto('/talk/almost');
            await expect(
                mainArea(page).getByText('回答 47', { exact: true }),
            ).toBeVisible();
            // 別のタブで 50 件に達した
            server.sessions.set('almost', {
                id: 'almost',
                title: '上限の手前のチャット',
                config_name: 'plain',
                messages: history(50),
            });
            await failNextTurn(page, 400, {
                error: '1 セッションのメッセージ数上限(50)に達しました',
            });

            await sendText(page, '競合した本文');

            await expect(page.getByRole('alert')).toContainText(
                'メッセージ数上限',
            );
            await expect(composer(page)).toHaveValue('競合した本文');
            await expect(
                mainArea(page).getByText('回答 49', { exact: true }),
            ).toBeVisible();
            await expect(sendButton(page)).toBeDisabled();
            await expect(
                page
                    .getByRole('status')
                    .getByRole('link', { name: '新しいチャット' }),
            ).toBeVisible();
        });

        test('上限でも編集はできる（件数が増えないため）', async ({ page }) => {
            server.sessions.set('full', {
                id: 'full',
                title: '上限のチャット',
                config_name: 'plain',
                messages: history(50),
            });
            await page.goto('/talk/full');
            await page
                .getByRole('button', { name: '編集', exact: true })
                .last()
                .click({ force: true });
            await page
                .getByRole('textbox', { name: 'メッセージを編集' })
                .fill('最後の発話を直す');

            await page
                .getByRole('button', { name: '送信して置き換える' })
                .click();

            await expect
                .poll(async () => (await turnsOf(page))[0]?.method)
                .toBe('PATCH');
        });
    });

    test.describe('音声', () => {
        const newTurn = {
            user: message(3, 2, 'user', '音声の確認'),
            assistant: message(4, 3, 'assistant', '音声付きの応答'),
        };

        test('保存された音声のプレーヤーとサイズとダウンロードを出す', async ({
            page,
        }) => {
            await page.goto('/talk/s1');

            await expect(
                page.getByRole('button', { name: '再生', exact: true }),
            ).toBeVisible();
            await expect(mainArea(page).getByText('1.0 KB')).toBeVisible();
            await expect(
                page.getByRole('button', { name: 'ダウンロード' }),
            ).toBeVisible();
        });

        test('合成中の表示のあいだも次を入力でき、届くとプレーヤーに替わる', async ({
            page,
        }) => {
            await page.goto('/talk/s1');
            await sendText(page, '音声の確認');
            await pushEvent(page, 0, 'delta', { text: '音声付きの応答' });
            await pushEvent(page, 0, 'message', newTurn);

            await expect(page.getByText('音声を合成中…')).toBeVisible();
            await expect(stopButton(page)).toHaveCount(0);
            await composer(page).fill('次の発話');
            await expect(sendButton(page)).toBeEnabled();

            await pushEvent(page, 0, 'audio', {
                message_id: 4,
                audio_url: '/talk/sessions/s1/audio/4/',
                audio_format: 'wav',
                audio_size_bytes: 2048,
            });

            await expect(page.getByText('音声を合成中…')).toHaveCount(0);
            await expect(mainArea(page).getByText('2.0 KB')).toBeVisible();
            await expect(composer(page)).toHaveValue('次の発話');
        });

        test('合成に失敗しても本文を残して文言を出す', async ({ page }) => {
            await page.goto('/talk/s1');
            await sendText(page, '音声の確認');
            await pushEvent(page, 0, 'message', newTurn);
            await pushEvent(page, 0, 'audio_error', {
                message_id: 4,
                error: '音声合成に失敗しました',
            });

            await expect(
                page.getByText('音声合成に失敗しました'),
            ).toBeVisible();
            await expect(
                mainArea(page).getByText('音声付きの応答'),
            ).toBeVisible();
        });

        test('音声が無効なプリセットでは合成中を出さない', async ({ page }) => {
            await page.goto('/talk/s2');
            await sendText(page, '続きの発話');
            await pushEvent(page, 0, 'message', {
                user: message(13, 2, 'user', '続きの発話'),
                assistant: message(14, 3, 'assistant', '音声なしの応答'),
            });

            await expect(
                mainArea(page).getByText('音声なしの応答'),
            ).toBeVisible();
            await expect(page.getByText('音声を合成中…')).toHaveCount(0);
        });

        test('確認ダイアログの確定を続けて押しても 1 回だけ実行する', async ({
            page,
        }) => {
            await page.goto('/talk/s1');
            await page.getByRole('button', { name: '音声を全削除' }).click();

            await clickTwice(
                page,
                page.getByRole('button', { name: '全て削除' }),
            );

            expect(server.mutations).toEqual([
                'DELETE talk/sessions/s1/audio/',
            ]);
            await expect(
                page.getByRole('button', { name: '音声を全削除' }),
            ).toHaveCount(0);
        });

        test('確認ダイアログをキャンセルすると何も実行しない', async ({
            page,
        }) => {
            await page.goto('/talk/s1');
            await page.getByRole('button', { name: '音声を全削除' }).click();

            const dialog = page.getByRole('alertdialog');
            await expect(
                dialog.getByRole('button', { name: 'キャンセル' }),
            ).toBeFocused();
            await dialog.getByRole('button', { name: 'キャンセル' }).click();

            await expect(dialog).toBeHidden();
            expect(server.mutations).toEqual([]);
        });

        test('1 件の音声を削除すると本文は残る', async ({ page }) => {
            await page.goto('/talk/s1');

            await page.getByRole('button', { name: '音声を削除' }).click();
            await page
                .getByRole('alertdialog')
                .getByRole('button', { name: '削除' })
                .click();

            await expect(
                page.getByRole('button', { name: '再生', exact: true }),
            ).toHaveCount(0);
            await expect(
                mainArea(page).getByText('おはようございます！'),
            ).toBeVisible();
            expect(server.mutations).toEqual([
                'DELETE talk/sessions/s1/audio/2/',
            ]);
        });
    });

    test.describe('URL の復元', () => {
        test('URL を直接開くと会話を出し、再読み込みしても同じチャットにいる', async ({
            page,
        }) => {
            await page.goto('/talk/s2');
            await expect(mainArea(page).getByText('元の応答')).toBeVisible();
            await expect(
                page.getByRole('link', { name: /音声なしの話/ }),
            ).toHaveAttribute('aria-current', 'page');

            await page.reload();

            await expect(page).toHaveURL('/talk/s2');
            await expect(mainArea(page).getByText('元の応答')).toBeVisible();
        });

        test('存在しないセッションなら /talk へ移って知らせる', async ({
            page,
        }) => {
            await page.goto('/talk/gone');

            await expect(page).toHaveURL('/talk');
            await expect(page.getByRole('alert')).toContainText(
                'チャットが見つかりません',
            );
            await expect(mainArea(page).getByText('TALK')).toBeVisible();
        });

        test('一覧のリンクで切り替え、切り替えると入力を空にする', async ({
            page,
        }) => {
            await page.goto('/talk/s1');
            await composer(page).fill('下書き');

            await page.getByRole('link', { name: /音声なしの話/ }).click();

            await expect(page).toHaveURL('/talk/s2');
            await expect(mainArea(page).getByText('元の応答')).toBeVisible();
            await expect(composer(page)).toHaveValue('');
        });
    });

    test.describe('入力', () => {
        test('Shift+Enter で改行し、Enter で送る', async ({ page }) => {
            await page.goto('/talk/s2');
            await composer(page).fill('1 行目');

            await composer(page).press('Shift+Enter');
            await composer(page).pressSequentially('2 行目');
            await expect(composer(page)).toHaveValue('1 行目\n2 行目');

            await composer(page).press('Enter');

            await expect(composer(page)).toHaveValue('');
            await expect
                .poll(async () => (await turnsOf(page))[0]?.content)
                .toBe('1 行目\n2 行目');
        });

        test('IME で変換中の Enter では送らず、確定後の Enter で送る', async ({
            page,
        }) => {
            await page.goto('/talk/s2');
            await composer(page).click();
            const cdp = await page.context().newCDPSession(page);

            await cdp.send('Input.imeSetComposition', {
                text: 'かな',
                selectionStart: 2,
                selectionEnd: 2,
            });
            await expect(composer(page)).toHaveValue('かな');
            // 変換中の Enter は、IME がキーコード 229 で keydown を渡す
            for (const type of ['rawKeyDown', 'keyUp'] as const) {
                await cdp.send('Input.dispatchKeyEvent', {
                    type,
                    windowsVirtualKeyCode: 229,
                    key: 'Enter',
                    code: 'Enter',
                });
            }

            await expect(composer(page)).toHaveValue('かな');
            expect(await turnsOf(page)).toEqual([]);

            await cdp.send('Input.insertText', { text: 'かな' });
            await page.keyboard.press('Enter');

            await expect(composer(page)).toHaveValue('');
            await expect
                .poll(async () => (await turnsOf(page))[0]?.content)
                .toBe('かな');
        });

        test('4000 字を超えても切り詰めず、送信を止める', async ({ page }) => {
            await page.goto('/talk/s2');
            const tooLong = 'あ'.repeat(4001);

            await composer(page).fill(tooLong);

            await expect(composer(page)).toHaveValue(tooLong);
            await expect(page.getByText('4001 / 4000')).toBeVisible();
            await expect(sendButton(page)).toBeDisabled();
            await composer(page).press('Enter');
            await expect(composer(page)).toHaveValue(tooLong);
            expect(await turnsOf(page)).toEqual([]);
        });
    });

    test.describe('Markdown', () => {
        test('生の HTML を実行せず、表とコードとリンクを描画する', async ({
            page,
        }) => {
            let dialogShown = false;
            page.on('dialog', (dialog) => {
                dialogShown = true;
                void dialog.dismiss();
            });
            server.sessions.set('md', {
                id: 'md',
                title: 'Markdown',
                config_name: 'plain',
                messages: [
                    message(1, 0, 'user', '<b>発話はそのまま</b>'),
                    message(
                        2,
                        1,
                        'assistant',
                        [
                            '<img src=x onerror="alert(1)"><script>alert(2)</script>',
                            '',
                            '| 列 |',
                            '| --- |',
                            '| 値 |',
                            '',
                            '```python',
                            'print(1)',
                            '```',
                            '',
                            '[リンク](https://example.com/)',
                            '',
                            '[危険](javascript:alert(3))',
                        ].join('\n'),
                    ),
                ],
            });

            await page.goto('/talk/md');

            await expect(page.getByRole('table')).toBeVisible();
            await expect(mainArea(page).locator('pre')).toContainText(
                'print(1)',
            );
            await expect(mainArea(page).locator('img')).toHaveCount(0);
            await expect(mainArea(page).locator('script')).toHaveCount(0);
            await expect(
                mainArea(page).getByText('<b>発話はそのまま</b>'),
            ).toBeVisible();
            const link = page.getByRole('link', {
                name: 'リンク',
                exact: true,
            });
            await expect(link).toHaveAttribute('target', '_blank');
            await expect(link).toHaveAttribute('rel', 'noreferrer noopener');
            await expect(mainArea(page).getByText('危険')).not.toHaveAttribute(
                'href',
                /javascript/,
            );
            expect(dialogShown).toBe(false);
        });
    });

    test.describe('一覧', () => {
        test('チャット以外のページでは一覧を出さない', async ({ page }) => {
            await page.goto('/tts');

            await expect(
                page.getByRole('link', { name: '新しいチャット' }),
            ).toHaveCount(0);
        });

        test('チャットを確認して削除すると一覧から消え、表示中なら /talk へ移る', async ({
            page,
        }) => {
            await page.goto('/talk/s1');
            await expect(
                mainArea(page).getByText('おはようございます！'),
            ).toBeVisible();

            await page.getByRole('link', { name: /朝の挨拶の練習/ }).hover();
            await page
                .getByRole('button', { name: '「朝の挨拶の練習」を削除' })
                .click();
            await page
                .getByRole('alertdialog')
                .getByRole('button', { name: '削除' })
                .click();

            await expect(page).toHaveURL('/talk');
            await expect(
                page.getByRole('link', { name: /朝の挨拶の練習/ }),
            ).toHaveCount(0);
            expect(server.mutations).toEqual(['DELETE talk/sessions/s1/']);
        });

        test('タイトルを編集すると一覧にも反映する', async ({ page }) => {
            await page.goto('/talk/s2');

            await page.getByRole('button', { name: 'タイトルを編集' }).click();
            await page.getByRole('textbox', { name: 'タイトル' }).fill('新題');
            await page
                .getByRole('textbox', { name: 'タイトル' })
                .press('Enter');

            await expect(
                mainArea(page).getByRole('heading', { name: '新題' }),
            ).toBeVisible();
            await expect(
                page.getByRole('link', { name: /新題/ }),
            ).toBeVisible();
        });
    });

    test.describe('画面', () => {
        test('ページに h1 が 1 つある', async ({ page }) => {
            await page.goto('/talk');
            await expect(page.locator('h1')).toHaveCount(1);

            await page.goto('/talk/s1');
            await expect(
                mainArea(page).getByText('おはようございます！'),
            ).toBeVisible();
            await expect(page.locator('h1')).toHaveCount(1);
        });

        test('高さの低い画面でも入力欄に届く', async ({ page }) => {
            await page.setViewportSize({ width: 844, height: 390 });
            await page.goto('/talk/s1');
            await expect(
                mainArea(page).getByText('おはようございます！'),
            ).toBeVisible();

            await expect(composer(page)).toBeInViewport({ ratio: 1 });
            await expect(sendButton(page)).toBeInViewport({ ratio: 1 });
        });

        test('スマホ幅で長い URL と表を出しても横にはみ出さない', async ({
            page,
        }) => {
            await page.setViewportSize({ width: 390, height: 844 });
            server.sessions.set('wide', {
                id: 'wide',
                title: '横にはみ出しやすい内容',
                config_name: 'plain',
                messages: [
                    message(
                        1,
                        0,
                        'user',
                        `https://example.com/${'long/'.repeat(40)}`,
                    ),
                    message(
                        2,
                        1,
                        'assistant',
                        [
                            `https://example.com/${'long/'.repeat(40)}`,
                            '',
                            `| ${Array(12).fill('見出し').join(' | ')} |`,
                            `| ${Array(12).fill('---').join(' | ')} |`,
                            `| ${Array(12).fill('値').join(' | ')} |`,
                            '',
                            '```',
                            'x'.repeat(300),
                            '```',
                        ].join('\n'),
                    ),
                ],
            });

            await page.goto('/talk/wide');
            await expect(page.getByRole('table')).toBeVisible();

            const overflow = await page.evaluate(() => {
                const viewport = document.querySelector(
                    '[data-aui-thread-root] > .overflow-y-auto',
                ) as HTMLElement;
                return {
                    page: document.documentElement.scrollWidth - innerWidth,
                    viewport: viewport.scrollWidth - viewport.clientWidth,
                };
            });
            expect(overflow).toEqual({ page: 0, viewport: 0 });
        });

        test('スマホ幅ではドロワーから一覧を開いて切り替え、閉じる', async ({
            page,
        }) => {
            await page.setViewportSize({ width: 390, height: 844 });
            await page.goto('/talk/s1');

            await page.getByRole('button', { name: 'メニューを開く' }).click();
            await page
                .getByRole('complementary')
                .getByRole('link', { name: /音声なしの話/ })
                .first()
                .click();

            await expect(page).toHaveURL('/talk/s2');
            await expect(mainArea(page).getByText('元の応答')).toBeVisible();
            await expect(
                page.getByRole('complementary').first(),
            ).toHaveAttribute('inert');
        });
    });
});

test.describe('タッチの環境', () => {
    test.use({
        viewport: { width: 390, height: 844 },
        hasTouch: true,
        isMobile: true,
    });

    test('一覧の削除ボタンとアクションが常に見え、開いただけではキーボードを出さない', async ({
        page,
    }) => {
        await mockApi(page);
        await page.goto('/login');
        await page.evaluate(() => {
            localStorage.setItem('auth-token', 'fake-token');
            localStorage.setItem('auth-email', 'test@example.com');
        });

        await page.goto('/talk/s2');

        await expect(mainArea(page).getByText('元の応答')).toBeVisible();
        await expect(composer(page)).not.toBeFocused();
        await expect(
            page.getByRole('button', { name: '編集', exact: true }),
        ).toHaveCSS('opacity', '1');

        await page.getByRole('button', { name: 'メニューを開く' }).tap();
        const remove = page.getByRole('button', {
            name: '「音声なしの話」を削除',
        });
        await expect(remove.first()).toHaveCSS('opacity', '1');
        await remove.first().tap();

        await expect(page.getByRole('alertdialog')).toBeVisible();
    });
});
