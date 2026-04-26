import { Home, Image, MessagesSquare, Mic } from 'lucide-react';

export const navItems = [
    { to: '/', label: 'ホーム', icon: Home },
    { to: '/tts', label: 'テキスト読み上げ', icon: Mic },
    { to: '/talk', label: 'チャット', icon: MessagesSquare },
    { to: '/media', label: 'メディア変換', icon: Image },
] as const;
