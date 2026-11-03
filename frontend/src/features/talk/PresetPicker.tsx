import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { useChatStore } from '@/stores/chat-store';

/** プリセットの表示。作成後は変えられないので、選べるのは新規チャットのときだけ。 */
export function PresetPicker() {
    const configs = useChatStore((s) => s.configs);
    const selected = useChatStore((s) => s.selectedConfigName);
    const selectConfig = useChatStore((s) => s.selectConfig);
    const activeSession = useChatStore((s) => s.activeSession);

    if (activeSession) {
        const name = activeSession.config_name;
        return (
            <span className="text-ink-subtle text-xs tracking-[0.04em] whitespace-nowrap">
                {configs.find((c) => c.name === name)?.display_name ?? name}
            </span>
        );
    }

    return (
        <Select value={selected ?? ''} onValueChange={selectConfig}>
            <SelectTrigger
                className="mx-auto w-auto min-w-44"
                aria-label="プリセット"
                disabled={configs.length === 0}
            >
                <SelectValue placeholder="プリセットを選択" />
            </SelectTrigger>
            <SelectContent>
                {configs.map((c) => (
                    <SelectItem key={c.name} value={c.name}>
                        {c.display_name}
                    </SelectItem>
                ))}
            </SelectContent>
        </Select>
    );
}
