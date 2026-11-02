import path from 'path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
    plugins: [react(), tailwindcss()],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
    build: {
        // 既定（4KB 未満をインライン）だと和文書体の小さいサブセットが base64 で CSS に
        // 埋め込まれ、描画を止める CSS が大きく膨らむ。必要な分だけ読まれるよう分離する。
        assetsInlineLimit: 0,
    },
    server: {
        proxy: {
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true,
                rewrite: (p) => p.replace(/^\/api/, ''),
            },
        },
    },
});
