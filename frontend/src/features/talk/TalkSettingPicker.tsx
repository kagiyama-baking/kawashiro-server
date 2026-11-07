import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { useChatStore } from '@/stores/chat-store';
import type { ChatSessionListItem, TalkScene } from '@/types/talk';

// Radix の Select は空文字の値を受け付けないので、「なし」は専用の値で表す。
// スキル名は英小文字・数字・ハイフンだけなので重ならない
const NO_SCENE = '__none__';

const TRIGGER_CLASS = 'w-auto max-w-full min-w-44';

const NO_SETTINGS =
    '選べる Talk 設定がありません。管理画面の Talk → Talk 設定で有効にしてください。';

function sessionSettingLabel(session: ChatSessionListItem): string {
    if (session.setting === null) return '（Talk 設定なし）';
    return session.skill === null
        ? session.setting.name
        : `${session.setting.name} · ${session.skill.description}`;
}

function SceneSelect({ scenes }: { readonly scenes: readonly TalkScene[] }) {
    const selectedName = useChatStore((s) => s.selectedSkillName);
    const selectSkill = useChatStore((s) => s.selectSkill);
    const selected = scenes.find((scene) => scene.name === selectedName);

    return (
        <Select
            value={selectedName ?? NO_SCENE}
            onValueChange={(value) =>
                selectSkill(value === NO_SCENE ? null : value)
            }
        >
            <SelectTrigger className={TRIGGER_CLASS} aria-label="シーン">
                {/* 選択肢には名前も添えるが、選んだ後は説明だけを出す */}
                <SelectValue>
                    <span className="truncate">
                        {selected?.description ?? 'なし'}
                    </span>
                </SelectValue>
            </SelectTrigger>
            <SelectContent>
                <SelectItem value={NO_SCENE}>なし</SelectItem>
                {scenes.map((scene) => (
                    <SelectItem key={scene.name} value={scene.name}>
                        <span className="flex flex-col">
                            <span>{scene.description}</span>
                            <span className="font-latin text-ink-subtle text-xs">
                                {scene.name}
                            </span>
                        </span>
                    </SelectItem>
                ))}
            </SelectContent>
        </Select>
    );
}

/** 新規チャットの Talk 設定と、その設定のシーン（任意）の選択。 */
function NewChatPicker() {
    const settings = useChatStore((s) => s.settings);
    const selectedId = useChatStore((s) => s.selectedSettingId);
    const selectSetting = useChatStore((s) => s.selectSetting);
    const scenes = settings?.find((s) => s.id === selectedId)?.skills ?? [];

    return (
        <div className="flex max-w-full flex-col items-center gap-2">
            <div className="flex max-w-full flex-wrap justify-center gap-2">
                <Select
                    value={selectedId === null ? '' : String(selectedId)}
                    onValueChange={(value) => selectSetting(Number(value))}
                >
                    <SelectTrigger
                        className={TRIGGER_CLASS}
                        aria-label="Talk 設定"
                        disabled={!settings?.length}
                    >
                        <SelectValue placeholder="Talk 設定を選択" />
                    </SelectTrigger>
                    <SelectContent>
                        {settings?.map((setting) => (
                            <SelectItem
                                key={setting.id}
                                value={String(setting.id)}
                            >
                                {setting.name}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
                {scenes.length > 0 && <SceneSelect scenes={scenes} />}
            </div>
            {settings?.length === 0 && (
                <p className="text-ink-subtle text-xs">{NO_SETTINGS}</p>
            )}
        </div>
    );
}

/** Talk 設定とシーン。作成後は変えられないので、選べるのは新規チャットのときだけ。 */
export function TalkSettingPicker() {
    const activeSession = useChatStore((s) => s.activeSession);

    if (activeSession === null) return <NewChatPicker />;

    const label = sessionSettingLabel(activeSession);
    // ヘッダではタイトルを優先する。シーンの説明は長くなりうるので幅を抑えて切り詰め、全文は title で出す
    return (
        <span
            title={label}
            className="text-ink-subtle max-w-[40%] truncate text-xs tracking-[0.04em]"
        >
            {label}
        </span>
    );
}
