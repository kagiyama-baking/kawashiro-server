import { Outlet } from 'react-router';
import { Sidebar } from './Sidebar';

export function AppLayout() {
    return (
        <div className="bg-background flex h-svh flex-col overflow-hidden lg:flex-row">
            <Sidebar />
            <main className="relative min-h-0 min-w-0 flex-1 overflow-y-auto">
                {/* 余白を変えたら ChatPage の高さも追従する（どちらも tokens.css の値を読む） */}
                <div className="px-(--page-pad-x) pt-(--page-pad-top) pb-(--page-pad-bottom)">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
