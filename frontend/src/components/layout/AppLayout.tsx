import { Outlet, useMatch } from 'react-router';
import { Sidebar } from './Sidebar';

export function AppLayout() {
    // チャットは自前でスクロールし、余白も持つ
    const isChat = useMatch('/talk/*') !== null;

    return (
        <div className="bg-background flex h-svh flex-col overflow-hidden lg:flex-row">
            <Sidebar />
            {isChat ? (
                <main className="relative min-h-0 min-w-0 flex-1 overflow-hidden">
                    <Outlet />
                </main>
            ) : (
                <main className="relative min-h-0 min-w-0 flex-1 overflow-y-auto">
                    <div className="px-(--page-pad-x) pt-(--page-pad-top) pb-(--page-pad-bottom)">
                        <Outlet />
                    </div>
                </main>
            )}
        </div>
    );
}
