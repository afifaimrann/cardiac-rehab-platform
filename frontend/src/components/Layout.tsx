import { HeartPulse, LogOut } from "lucide-react";
import type { ReactNode } from "react";
import { useAuth } from "@/context/auth";
import { Button } from "@/components/ui";

export function Layout({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-full">
      <header className="border-b border-ink-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-600 text-white">
              <HeartPulse size={16} strokeWidth={2.4} />
            </div>
            <span className="text-[14px] font-semibold tracking-tight text-ink-900">Cardiac Rehab</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <p className="text-[13px] font-medium leading-tight text-ink-800">{user?.full_name}</p>
              <p className="text-[11px] uppercase tracking-wide text-ink-400">{user?.role}</p>
            </div>
            <Button variant="ghost" size="sm" onClick={logout} aria-label="Sign out">
              <LogOut size={15} />
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-7">
        <div className="mb-6">
          <h1 className="text-xl font-semibold tracking-tight text-ink-900">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-ink-500">{subtitle}</p>}
        </div>
        {children}
      </main>
    </div>
  );
}
