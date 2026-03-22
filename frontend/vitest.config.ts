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
            include: ['src/**/*.{ts,tsx}'],
            exclude: [
                'src/main.tsx',
                'src/vite-env.d.ts',
                'src/components/ui/**',
            ],
            thresholds: {
                lines: 80,
            },
        },
    },
});
