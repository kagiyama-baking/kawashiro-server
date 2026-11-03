import path from 'path';
import { defineConfig } from 'vitest/config';

export default defineConfig({
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
    test: {
        globals: true,
        environment: 'jsdom',
        setupFiles: ['./tests/setup.ts'],
        exclude: ['e2e/**', 'node_modules/**'],
        css: true,
        coverage: {
            provider: 'v8',
            include: [
                'src/stores/**',
                'src/lib/**',
                'src/components/auth/**',
            ],
            // pdf-worker.ts は副作用（pdf.js Worker URL 設定）のみで、
            // jsdom 環境では `?url` の解決が必要なためユニットテストの対象外。
            exclude: ['src/lib/pdf/pdf-worker.ts'],
            thresholds: {
                lines: 80,
            },
        },
    },
});
