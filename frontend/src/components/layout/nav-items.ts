import { Home, Image, MessagesSquare, Mic, Sparkles } from 'lucide-react';

export const navItems = [
    { to: '/', label: 'ホーム', icon: Home },
    { to: '/tts', label: 'テキスト読み上げ', icon: Mic },
    { to: '/talk', label: '会話生成読み上げ', icon: Sparkles },
    { to: '/talk/chat', label: '会話チャット', icon: MessagesSquare },
    { to: '/media', label: 'メディア変換', icon: Image },
] as const;
