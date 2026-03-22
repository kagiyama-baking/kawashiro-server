import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { useTtsStore } from '@/stores/tts-store';
import { TTS_PARAM_CONFIGS } from '@/types/tts';

export function TtsParamSliders() {
    const params = useTtsStore((s) => s.params);
    const setParam = useTtsStore((s) => s.setParam);

    return (
        <div className="space-y-4">
            {TTS_PARAM_CONFIGS.map(({ key, label, min, max, step }) => (
                <div key={key} className="space-y-2">
                    <div className="flex items-center justify-between">
                        <Label className="text-sm">{label}</Label>
                        <span className="text-sm text-muted-foreground">
                            {params[key]}
                        </span>
                    </div>
                    <Slider
                        value={[params[key]]}
                        min={min}
                        max={max}
                        step={step}
                        onValueChange={([v]) => setParam(key, v)}
                        aria-label={label}
                    />
                </div>
            ))}
        </div>
    );
}
