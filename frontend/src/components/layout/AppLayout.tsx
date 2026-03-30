import { Outlet } from 'react-router';
import { Sidebar } from './Sidebar';

export function AppLayout() {
    return (
        <div className="bg-background flex h-svh overflow-hidden">
            <Sidebar />
            <main className="relative flex-1 overflow-auto">
                {/* ドットグリッド背景 */}
                <div
                    className="pointer-events-none absolute inset-0 opacity-[0.02]"
                    style={{
                        backgroundImage:
                            'radial-gradient(oklch(0.75 0.20 155) 1px, transparent 1px)',
                        backgroundSize: '24px 24px',
                    }}
                />
                <div className="relative pt-16 pr-6 pb-8 pl-14 lg:px-10 lg:pt-8 lg:pb-10">
                    <Outlet />
                </div>
            </main>
        </div>
    );
}
