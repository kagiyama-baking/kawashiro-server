import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { fetchConfigs, generateText } from '@/lib/api/generate';
import type { GenerateConfig, GenerateResult } from '@/types/generate';

export function useGenerate() {
    const [configs, setConfigs] = useState<GenerateConfig[]>([]);
    const [selectedConfig, setSelectedConfig] = useState<string>('');
    const [result, setResult] = useState<GenerateResult | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const previousUrlRef = useRef<string | null>(null);

    useEffect(() => {
        fetchConfigs()
            .then((c) => {
                setConfigs(c);
                if (c.length > 0) {
                    setSelectedConfig(c[0].name);
                }
            })
            .catch(() => setError('設定一覧の取得に失敗しました'));
    }, []);

    const handleGenerate = useCallback(
        async (userPrompt: string) => {
            if (!selectedConfig || !userPrompt.trim()) return;

            setIsLoading(true);
            setError(null);

            if (previousUrlRef.current) {
                URL.revokeObjectURL(previousUrlRef.current);
            }

            try {
                const generateResult = await generateText({
                    config_name: selectedConfig,
                    user_prompt: userPrompt,
                });
                if (generateResult.audioUrl) {
                    previousUrlRef.current = generateResult.audioUrl;
                }
                setResult(generateResult);
                toast.success('テキストを生成しました');
            } catch {
                setError('テキスト生成に失敗しました');
                toast.error('テキスト生成に失敗しました');
            } finally {
                setIsLoading(false);
            }
        },
        [selectedConfig],
    );

    useEffect(() => {
        return () => {
            if (previousUrlRef.current) {
                URL.revokeObjectURL(previousUrlRef.current);
            }
        };
    }, []);

    return {
        configs,
        selectedConfig,
        setSelectedConfig,
        result,
        isLoading,
        error,
        handleGenerate,
    } as const;
}
