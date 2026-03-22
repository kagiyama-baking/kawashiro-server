import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { fetchModels, fetchStyles, synthesize } from '@/lib/api/tts';
import { useTtsStore } from '@/stores/tts-store';

export function useTts() {
    const [models, setModels] = useState<string[]>([]);
    const [styles, setStyles] = useState<string[]>([]);
    const [selectedModel, setSelectedModel] = useState<string>('');
    const [audioUrl, setAudioUrl] = useState<string | null>(null);
    const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const params = useTtsStore((s) => s.params);
    const previousUrlRef = useRef<string | null>(null);

    useEffect(() => {
        fetchModels()
            .then((m) => {
                setModels(m);
                if (m.length > 0) {
                    setSelectedModel(m[0]);
                }
            })
            .catch(() => setError('モデル一覧の取得に失敗しました'));
    }, []);

    useEffect(() => {
        if (!selectedModel) return;
        fetchStyles(selectedModel)
            .then(setStyles)
            .catch(() => setError('スタイル一覧の取得に失敗しました'));
    }, [selectedModel]);

    const handleSynthesize = useCallback(
        async (text: string) => {
            if (!text.trim()) return;

            setIsLoading(true);
            setError(null);

            // 前回のURLをクリーンアップ
            if (previousUrlRef.current) {
                URL.revokeObjectURL(previousUrlRef.current);
            }

            try {
                const blob = await synthesize({
                    text,
                    model: selectedModel || undefined,
                    ...params,
                });
                const url = URL.createObjectURL(blob);
                previousUrlRef.current = url;
                setAudioBlob(blob);
                setAudioUrl(url);
                toast.success('音声を生成しました');
            } catch {
                setError('音声合成に失敗しました');
                toast.error('音声合成に失敗しました');
            } finally {
                setIsLoading(false);
            }
        },
        [selectedModel, params],
    );

    // コンポーネントアンマウント時にURLをクリーンアップ
    useEffect(() => {
        return () => {
            if (previousUrlRef.current) {
                URL.revokeObjectURL(previousUrlRef.current);
            }
        };
    }, []);

    return {
        models,
        styles,
        selectedModel,
        setSelectedModel,
        audioUrl,
        audioBlob,
        isLoading,
        error,
        handleSynthesize,
    } as const;
}
