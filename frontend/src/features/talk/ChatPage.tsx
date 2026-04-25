import { Trash2 } from 'lucide-react';
import { ErrorMessage } from '@/components/common/ErrorMessage';
import { TerminalText } from '@/components/common/TerminalText';
import { Button } from '@/components/ui/button';
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { ChatInputForm } from './ChatInputForm';
import { ChatMessageList } from './ChatMessageList';
import { useChat } from './useChat';

export function ChatPage() {
    const {
        configs,
        selectedConfig,
        setSelectedConfig,
        input,
        setInput,
        messages,
        isLoading,
        error,
        sendMessage,
        clearHistory,
    } = useChat();

    const selected = configs.find((c) => c.name === selectedConfig);

    return (
        <div className="mx-auto max-w-4xl space-y-6">
            <div className="animate-slide-up">
                <h1 className="font-heading text-foreground text-2xl font-bold tracking-tight">
                    会話チャット
                </h1>
                <TerminalText text="talk --chat" />
            </div>

            <Card className="animate-slide-up neon-border">
                <CardHeader>
                    <div className="flex items-start justify-between gap-3">
                        <div className="space-y-1">
                            <CardTitle className="font-heading font-semibold">
                                セッション設定
                            </CardTitle>
                            <CardDescription className="text-[13px]">
                                プリセットを選んで連続的に会話できます。履歴はブラウザを更新するとクリアされます。
                            </CardDescription>
                        </div>
                        <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={clearHistory}
                            disabled={messages.length === 0}
                            className="shrink-0"
                        >
                            <Trash2 className="mr-1.5 h-4 w-4" />
                            履歴をクリア
                        </Button>
                    </div>
                </CardHeader>
                <CardContent className="space-y-4">
                    <div className="space-y-2">
                        <Label
                            htmlFor="chat-preset-select"
                            className="text-[13px] font-medium"
                        >
                            プリセット
                        </Label>
                        <Select
                            value={selectedConfig}
                            onValueChange={setSelectedConfig}
                        >
                            <SelectTrigger id="chat-preset-select">
                                <SelectValue placeholder="設定を選択" />
                            </SelectTrigger>
                            <SelectContent>
                                {configs.map((config) => (
                                    <SelectItem
                                        key={config.name}
                                        value={config.name}
                                    >
                                        {config.display_name}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        {selected?.tts_enabled && (
                            <div className="flex flex-wrap gap-2 text-xs">
                                <span className="rounded-md border border-[oklch(0.72_0.20_155/0.2)] bg-[oklch(0.72_0.20_155/0.1)] px-1.5 py-0.5 text-[oklch(0.72_0.20_155)]">
                                    TTS有効
                                </span>
                            </div>
                        )}
                    </div>

                    <Separator className="opacity-30" />

                    <ChatMessageList
                        messages={messages}
                        isLoading={isLoading}
                    />

                    <ChatInputForm
                        input={input}
                        onInputChange={setInput}
                        onSubmit={sendMessage}
                        isLoading={isLoading}
                        disabled={!selectedConfig}
                    />

                    <ErrorMessage message={error} />
                </CardContent>
            </Card>
        </div>
    );
}
