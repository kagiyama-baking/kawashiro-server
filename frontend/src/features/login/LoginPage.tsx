import { type FormEvent, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useLogin } from './useLogin';

export function LoginPage() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const { error, isLoading, handleLogin } = useLogin();

    const onSubmit = (e: FormEvent) => {
        e.preventDefault();
        handleLogin(email, password);
    };

    return (
        <div className="bg-background relative flex min-h-svh items-center justify-center overflow-hidden p-4">
            {/* 背景オーブ */}
            <div className="pointer-events-none absolute inset-0">
                <div
                    className="animate-float-orb absolute -top-32 -right-32 h-72 w-72 rounded-full bg-[oklch(0.75_0.20_155/0.08)] blur-3xl"
                    style={{ animationDelay: '-2s' }}
                />
                <div className="animate-float-orb absolute -bottom-20 -left-20 h-48 w-48 rounded-full bg-[oklch(0.72_0.20_155/0.06)] blur-3xl" />
            </div>

            <div className="glass neon-border relative w-full max-w-sm rounded-2xl p-6">
                <div className="mb-6 space-y-2 text-center">
                    <h1 className="font-heading neon-text text-2xl font-bold tracking-tight">
                        鍵山製パンWebApp
                    </h1>
                    <p className="text-muted-foreground text-sm">
                        ログインして続行してください
                    </p>
                    <div className="mx-auto h-px w-16 bg-gradient-to-r from-transparent via-[oklch(0.75_0.20_155/0.5)] to-transparent" />
                </div>

                <form onSubmit={onSubmit} className="space-y-4">
                    <div className="space-y-2">
                        <Label
                            htmlFor="email"
                            className="text-[13px] font-medium"
                        >
                            メールアドレス
                        </Label>
                        <Input
                            id="email"
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="email@example.com"
                            required
                            autoComplete="email"
                        />
                    </div>
                    <div className="space-y-2">
                        <Label
                            htmlFor="password"
                            className="text-[13px] font-medium"
                        >
                            パスワード
                        </Label>
                        <Input
                            id="password"
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            autoComplete="current-password"
                        />
                    </div>
                    {error && (
                        <p className="text-destructive text-[13px]">{error}</p>
                    )}
                    <Button
                        type="submit"
                        className="w-full font-semibold hover:shadow-[0_0_20px_oklch(0.75_0.20_155/0.4)]"
                        disabled={isLoading}
                    >
                        {isLoading ? 'ログイン中...' : 'ログイン'}
                    </Button>
                </form>
            </div>
        </div>
    );
}
