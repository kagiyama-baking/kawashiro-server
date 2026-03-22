import { Home, Image, Mic, Sparkles } from 'lucide-react';

export const navItems = [
    { to: '/', label: 'ホーム', icon: Home },
    { to: '/tts', label: 'テキスト読み上げ', icon: Mic },
    { to: '/generate', label: 'テキスト生成読み上げ', icon: Sparkles },
    { to: '/media', label: 'メディア変換', icon: Image },
] as const;
