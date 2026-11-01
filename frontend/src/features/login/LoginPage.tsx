import { type FormEvent, useState } from 'react';
import swirlMark from '@/assets/swirl.webp';
import { ErrorMessage } from '@/components/common/ErrorMessage';
import { PageHeader } from '@/components/common/PageHeader';
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
        <div className="bg-background flex min-h-svh items-center justify-center p-4">
            <div className="bg-card w-full max-w-sm rounded-lg border p-[1.6rem]">
                <img
                    src={swirlMark}
                    alt=""
                    width={34}
                    height={34}
                    className="mb-5 size-[34px]"
                />
                <PageHeader
                    eyebrow="Login"
                    title="鍵山製パンWebApp"
                    lead="ログインして続行してください"
                />

                <form onSubmit={onSubmit} className="space-y-4">
                    <div className="space-y-2">
                        <Label htmlFor="email">メールアドレス</Label>
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
                        <Label htmlFor="password">パスワード</Label>
                        <Input
                            id="password"
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            autoComplete="current-password"
                        />
                    </div>
                    <ErrorMessage message={error} />
                    <Button
                        type="submit"
                        className="w-full"
                        disabled={isLoading}
                    >
                        {isLoading ? 'ログイン中...' : 'ログイン'}
                    </Button>
                </form>
            </div>
        </div>
    );
}
