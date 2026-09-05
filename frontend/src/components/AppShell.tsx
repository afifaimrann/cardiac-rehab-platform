import { useEffect, useState, type ReactNode } from "react";
import {
  Activity, CalendarDays, Footprints, HeartPulse, LogOut, MessageCircle, Moon,
  Send, Settings, Sparkles, Sun, Users,
} from "lucide-react";
import { useAuth } from "@/context/auth";
import { api } from "@/lib/api";
import { applyTheme, storedTheme, type Theme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import { Avatar } from "@/components/Avatar";

export type NavKey =
  | "overview" | "ask" | "walk" | "appointments" | "messages" | "profile"
  | "caseload" | "assistant" | "diary";

/**
 * Application chrome: a narrow rail rather than a top bar, so the chat view can
 * own the full height of the window the way a real chat product does.
 */
export function AppShell({
  nav, active, onNavigate, children,
}: {
  nav?: NavKey[];
  active?: NavKey;
  onNavigate?: (key: NavKey) => void;
  children: ReactNode;
}) {
  const { user, logout } = useAuth();
  const [theme, setTheme] = useState<Theme>(() => storedTheme());
  const [unread, setUnread] = useState(0);

  useEffect(() => { applyTheme(theme); }, [theme]);

  // Poll rather than push: there is no socket in this build, and a badge that
  // is a minute stale is honest enough for a message a nurse answers in hours.
  useEffect(() => {
    if (user?.role !== "patient") return;
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await api.messages.unread();
        if (!cancelled) setUnread(r.unread_count);
      } catch { /* a badge is never worth an error */ }
    };
    void tick();
    const id = window.setInterval(tick, 60_000);
    return () => { cancelled = true; window.clearInterval(id); };
  }, [user?.role, active]);

  return (
    <div className="flex h-full">
      <aside className="flex w-[68px] shrink-0 flex-col items-center gap-1 border-e border-line bg-surface/60 py-4">
        <div className="mb-4 flex h-9 w-9 items-center justify-center rounded-[11px] bg-accent-500 text-white">
          <HeartPulse size={18} strokeWidth={2.3} />
        </div>

        {nav && nav.length > 0 && (
          <nav className="flex flex-col gap-1">
            {nav.map((key) => (
              <RailButton
                key={key}
                icon={NAV_ICON[key]}
                label={NAV_LABEL[key]}
                badge={key === "messages" ? unread : 0}
                active={active === key}
                onClick={() => onNavigate?.(key)}
              />
            ))}
          </nav>
        )}

        <div className="mt-auto flex flex-col items-center gap-2">
          <RailButton
            icon={theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
            label={theme === "dark" ? "Light mode" : "Dark mode"}
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          />
          <RailButton icon={<LogOut size={18} />} label="Sign out" onClick={logout} />
          <button
            title={user?.full_name}
            aria-label="Your profile"
            onClick={() => onNavigate?.("profile")}
            className="mt-1 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400/40"
          >
            <Avatar name={user?.full_name} src={user?.avatar_url} size={36} />
          </button>
        </div>
      </aside>

      <div className="min-w-0 flex-1 overflow-hidden">{children}</div>
    </div>
  );
}

const NAV_ICON: Record<NavKey, ReactNode> = {
  overview: <Activity size={19} />,
  ask: <MessageCircle size={19} />,
  walk: <Footprints size={19} />,
  appointments: <CalendarDays size={19} />,
  messages: <Send size={19} />,
  profile: <Settings size={19} />,
  caseload: <Users size={19} />,
  assistant: <Sparkles size={19} />,
  diary: <CalendarDays size={19} />,
};

const NAV_LABEL: Record<NavKey, string> = {
  overview: "Overview",
  ask: "Ask",
  walk: "Walk test",
  appointments: "Appointments",
  messages: "Your care team",
  profile: "Profile",
  caseload: "Caseload",
  assistant: "Ask about a patient",
  diary: "Diary",
};

function RailButton({ icon, label, active, badge = 0, onClick }: {
  icon: ReactNode; label: string; active?: boolean; badge?: number; onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      aria-label={badge > 0 ? `${label}, ${badge} unread` : label}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group relative flex h-10 w-10 items-center justify-center rounded-[11px] transition-colors duration-150",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-400/40",
        active ? "bg-accent-50 text-accent-500" : "text-ink-muted hover:bg-surface-sunk hover:text-ink",
      )}
    >
      {icon}
      {active && <span className="absolute -start-[9px] h-5 w-[3px] rounded-e-full bg-accent-500" />}
      {badge > 0 && (
        <span className="absolute -end-0.5 -top-0.5 flex h-[17px] min-w-[17px] items-center justify-center rounded-full bg-severe-fg px-1 text-[10px] font-bold text-white ring-2 ring-surface">
          {badge > 9 ? "9+" : badge}
        </span>
      )}
    </button>
  );
}

/** Shared measure. The header and the content below it must sit on the same
 *  grid, or the page reads as two designs stacked. */
export const CONTENT = "mx-auto w-full max-w-[1140px] px-8";

/** For tables. 1140px is a reading measure, chosen for prose and forms; a
 *  caseload has five columns and a queue beside it, and squeezing that into a
 *  measure meant for paragraphs is what makes a table scroll sideways. */
export const CONTENT_WIDE = "mx-auto w-full max-w-[1400px] px-8";

export function PageHeader({ title, subtitle, action, wide }: {
  title: string; subtitle?: string; action?: ReactNode; wide?: boolean;
}) {
  return (
    <header className="border-b border-line">
      <div className={`${wide ? CONTENT_WIDE : CONTENT} flex items-end justify-between gap-6 py-7`}>
        <div className="min-w-0">
          <h1 className="font-serif text-[30px] leading-[1.15] tracking-[-0.02em] text-ink">{title}</h1>
          {subtitle && <p className="mt-2 text-[14px] text-ink-muted">{subtitle}</p>}
        </div>
        {action}
      </div>
    </header>
  );
}
