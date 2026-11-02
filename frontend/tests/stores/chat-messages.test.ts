import { describe, expect, it } from 'vitest';
import {
    aggregateFromDetail,
    appendDelta,
    applyAudio,
    applyAudioError,
    applySaved,
    clearAudio,
    createLocalId,
    createUserMessage,
    finishPendingAudio,
    fromServerMessage,
    markCancelled,
    mergeServerMessages,
    replaceFromTarget,
} from '@/stores/chat-messages';
import type {
    ChatSessionDetail,
    ChatSessionMessage,
    ChatUiMessage,
} from '@/types/talk';

const NOW = '2026-11-02T09:30:00+09:00';

function serverMessage(
    overrides: Partial<ChatSessionMessage> = {},
): ChatSessionMessage {
    return {
        id: 1,
        sequence: 0,
        role: 'user',
        content: 'おはよう',
        audio_url: null,
        audio_format: '',
        audio_size_bytes: 0,
        created_at: NOW,
        ...overrides,
    };
}

function uiMessage(overrides: Partial<ChatUiMessage> = {}): ChatUiMessage {
    return {
        ...fromServerMessage(serverMessage()),
        ...overrides,
    };
}

describe('createLocalId', () => {
    it('呼ぶたびに別の local- で始まる id を返す', () => {
        const a = createLocalId();
        const b = createLocalId();

        expect(a).toMatch(/^local-/);
        expect(a).not.toBe(b);
    });
});

describe('fromServerMessage', () => {
    it('srv- で始まる localId を付け、完了済みとして扱う', () => {
        const message = fromServerMessage(serverMessage({ id: 42 }));

        expect(message).toMatchObject({
            localId: 'srv-42',
            id: 42,
            uiStatus: 'complete',
            audioState: 'idle',
            audioError: null,
        });
    });
});

describe('createUserMessage', () => {
    it('サーバーの値を持たない user の行を作る', () => {
        const message = createUserMessage('こんにちは');

        expect(message).toMatchObject({
            role: 'user',
            content: 'こんにちは',
            id: null,
            sequence: null,
            created_at: null,
            uiStatus: 'complete',
        });
        expect(message.localId).toMatch(/^local-/);
    });
});

describe('appendDelta', () => {
    it('assistant の行がなければ追加する', () => {
        const user = uiMessage();

        const next = appendDelta([user], 'local-a', 'こん');

        expect(next).toHaveLength(2);
        expect(next[0]).toBe(user);
        expect(next[1]).toMatchObject({
            localId: 'local-a',
            role: 'assistant',
            content: 'こん',
            id: null,
            uiStatus: 'streaming',
        });
    });

    it('assistant の行があれば差分を足した新しいオブジェクトにする', () => {
        const first = appendDelta([], 'local-a', 'こん');

        const next = appendDelta(first, 'local-a', 'にちは');

        expect(next[0].content).toBe('こんにちは');
        expect(next[0]).not.toBe(first[0]);
        expect(first[0].content).toBe('こん');
    });
});

describe('applySaved', () => {
    const user = serverMessage({ id: 10, sequence: 4, content: '保存後' });
    const assistant = serverMessage({
        id: 11,
        sequence: 5,
        role: 'assistant',
        content: '応答',
    });

    it('localId を変えずにサーバーの値を付ける', () => {
        const local = appendDelta(
            [uiMessage({ localId: 'local-u', id: null, sequence: null })],
            'local-a',
            '応',
        );

        const next = applySaved(local, {
            userLocalId: 'local-u',
            assistantLocalId: 'local-a',
            user,
            assistant,
            audioPending: false,
        });

        expect(next[0]).toMatchObject({
            localId: 'local-u',
            id: 10,
            sequence: 4,
            content: '保存後',
        });
        expect(next[1]).toMatchObject({
            localId: 'local-a',
            id: 11,
            sequence: 5,
            content: '応答',
            uiStatus: 'complete',
            audioState: 'idle',
        });
    });

    it('delta が 1 つも来なかったら assistant の行を追加する', () => {
        const next = applySaved([uiMessage({ localId: 'local-u' })], {
            userLocalId: 'local-u',
            assistantLocalId: 'local-a',
            user,
            assistant,
            audioPending: false,
        });

        expect(next.map((m) => m.localId)).toEqual(['local-u', 'local-a']);
        expect(next[1].id).toBe(11);
    });

    it('音声を待つときは assistant を pending にする', () => {
        const next = applySaved([uiMessage({ localId: 'local-u' })], {
            userLocalId: 'local-u',
            assistantLocalId: 'local-a',
            user,
            assistant,
            audioPending: true,
        });

        expect(next[1].audioState).toBe('pending');
    });
});

describe('applyAudio / applyAudioError / clearAudio', () => {
    const pending = uiMessage({ id: 2, audioState: 'pending' });
    const other = uiMessage({ id: 3 });

    it('対象の行に音声を付けて pending を解く', () => {
        const next = applyAudio([pending, other], {
            message_id: 2,
            audio_url: '/a/2/',
            audio_format: 'wav',
            audio_size_bytes: 10,
        });

        expect(next[0]).toMatchObject({
            audio_url: '/a/2/',
            audio_format: 'wav',
            audio_size_bytes: 10,
            audioState: 'idle',
        });
        expect(next[1]).toBe(other);
    });

    it('対象の行がなければ何も変えない', () => {
        const messages = [other];

        expect(
            applyAudio(messages, {
                message_id: 99,
                audio_url: '/a/',
                audio_format: 'wav',
                audio_size_bytes: 1,
            }),
        ).toEqual(messages);
    });

    it('失敗を記録する', () => {
        const next = applyAudioError([pending], 2, '合成に失敗しました');

        expect(next[0]).toMatchObject({
            audioState: 'failed',
            audioError: '合成に失敗しました',
        });
    });

    it('音声の情報を消す', () => {
        const withAudio = uiMessage({
            id: 2,
            audio_url: '/a/2/',
            audio_format: 'wav',
            audio_size_bytes: 10,
            audioState: 'failed',
            audioError: 'x',
        });

        const next = clearAudio([withAudio, other], (m) => m.id === 2);

        expect(next[0]).toMatchObject({
            audio_url: null,
            audio_format: '',
            audio_size_bytes: 0,
            audioState: 'idle',
            audioError: null,
        });
        expect(next[1]).toBe(other);
    });
});

describe('finishPendingAudio', () => {
    it('pending のまま残った行だけ idle に戻す', () => {
        const pending = uiMessage({ id: 2, audioState: 'pending' });
        const failed = uiMessage({ id: 3, audioState: 'failed' });

        const next = finishPendingAudio([pending, failed]);

        expect(next[0].audioState).toBe('idle');
        expect(next[1]).toBe(failed);
    });
});

describe('markCancelled', () => {
    it('ストリーム中の行だけ cancelled にする', () => {
        const done = uiMessage({ id: 2 });
        const streaming = uiMessage({
            localId: 'local-a',
            uiStatus: 'streaming',
        });

        const next = markCancelled([done, streaming]);

        expect(next[0]).toBe(done);
        expect(next[1].uiStatus).toBe('cancelled');
    });
});

describe('replaceFromTarget', () => {
    it('対象の本文を差し替え、以降の行を落とす。localId と id は保つ', () => {
        const a = uiMessage({ localId: 'srv-1', id: 1 });
        const b = uiMessage({ localId: 'srv-2', id: 2, sequence: 1 });
        const c = uiMessage({
            localId: 'srv-3',
            id: 3,
            sequence: 2,
            role: 'assistant',
        });

        const next = replaceFromTarget([a, b, c], 'srv-2', '直し');

        expect(next).toHaveLength(2);
        expect(next[0]).toBe(a);
        expect(next[1]).toMatchObject({
            localId: 'srv-2',
            id: 2,
            content: '直し',
        });
    });
});

describe('mergeServerMessages', () => {
    it('位置で対応付け、localId を保ったままサーバーの値で更新する', () => {
        const local = [
            uiMessage({ localId: 'local-u', id: null, sequence: null }),
            uiMessage({
                localId: 'local-a',
                id: null,
                sequence: null,
                role: 'assistant',
                content: '途中',
                uiStatus: 'cancelled',
            }),
        ];
        const server = [
            serverMessage({ id: 5, sequence: 0, content: 'おはよう' }),
            serverMessage({
                id: 6,
                sequence: 1,
                role: 'assistant',
                content: '途中まで',
            }),
        ];

        const next = mergeServerMessages(local, server);

        expect(next[0]).toMatchObject({ localId: 'local-u', id: 5 });
        expect(next[1]).toMatchObject({
            localId: 'local-a',
            id: 6,
            content: '途中まで',
            uiStatus: 'cancelled',
        });
    });

    it('サーバーにしかない行は srv- で追加し、ローカルにしかない行は落とす', () => {
        const local = [uiMessage({ localId: 'local-u' })];
        const extra = serverMessage({ id: 9, sequence: 1, role: 'assistant' });

        expect(
            mergeServerMessages(local, [serverMessage(), extra]).map(
                (m) => m.localId,
            ),
        ).toEqual(['local-u', 'srv-9']);
        expect(mergeServerMessages(local, [])).toEqual([]);
    });

    it('役割が違う位置は別の行として扱う', () => {
        const local = [uiMessage({ localId: 'local-u', role: 'user' })];

        const next = mergeServerMessages(local, [
            serverMessage({ id: 7, role: 'assistant' }),
        ]);

        expect(next[0].localId).toBe('srv-7');
    });

    it('音声合成の途中の行は、音声がまだ保存されていなければ pending を保つ', () => {
        const local = [
            uiMessage({ localId: 'srv-1', id: 1, audioState: 'pending' }),
        ];

        expect(
            mergeServerMessages(local, [serverMessage({ id: 1 })])[0]
                .audioState,
        ).toBe('pending');
        expect(
            mergeServerMessages(local, [
                serverMessage({ id: 1, audio_url: '/a/1/' }),
            ])[0].audioState,
        ).toBe('idle');
    });

    it('別の行に置き換わっていたら pending を引き継がない', () => {
        const local = [
            uiMessage({ localId: 'srv-1', id: 1, audioState: 'pending' }),
        ];

        expect(
            mergeServerMessages(local, [serverMessage({ id: 2 })])[0]
                .audioState,
        ).toBe('idle');
    });
});

describe('aggregateFromDetail', () => {
    it('詳細から一覧の項目を作る', () => {
        const detail: ChatSessionDetail = {
            id: 's1',
            title: 't',
            config_name: 'c',
            message_count: 0,
            total_audio_bytes: 0,
            created_at: NOW,
            updated_at: NOW,
            messages: [
                serverMessage({ audio_size_bytes: 10 }),
                serverMessage({ id: 2, audio_size_bytes: 5 }),
            ],
        };

        expect(aggregateFromDetail(detail)).toEqual({
            id: 's1',
            title: 't',
            config_name: 'c',
            message_count: 2,
            total_audio_bytes: 15,
            created_at: NOW,
            updated_at: NOW,
        });
    });
});
