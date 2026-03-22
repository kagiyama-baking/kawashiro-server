import { Outlet } from 'react-router';
import { Sidebar } from './Sidebar';

export function AppLayout() {
    return (
        <div className="flex h-svh overflow-hidden">
            <Sidebar />
            <main className="flex-1 overflow-auto p-4 pt-16 lg:p-6 lg:pt-6">
                <Outlet />
            </main>
        </div>
    );
}
