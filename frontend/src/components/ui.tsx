/**
 * Presentational primitives.
 *
 * Hand-rolled rather than pulled from a component library: the set is small,
 * and owning it keeps one visual language across the app.
 */
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { Severity } from "@/lib/types";

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn(
      "rounded-[14px] border border-line bg-surface",
      "shadow-[0_1px_2px_rgba(28,26,23,.04),0_8px_24px_-16px_rgba(28,26,23,.10)]",
      className,
    )}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-ink">{title}</h2>
        {subtitle && <p className="mt-1 text-[13px] leading-relaxed text-ink-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "icon";
};

export function Button({ variant = "primary", size = "md", className, ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex select-none items-center justify-center gap-2 rounded-[10px] font-medium",
        "transition-[background-color,border-color,color,box-shadow,transform] duration-150",
        "active:scale-[.985]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/40 focus-visible:ring-offset-2 focus-visible:ring-offset-paper",
        "disabled:pointer-events-none disabled:opacity-45",
        size === "sm" && "h-8 px-3 text-[13px]",
        size === "md" && "h-10 px-4 text-sm",
        size === "icon" && "h-10 w-10",
        variant === "primary" && "bg-teal-500 text-white hover:bg-teal-600 shadow-[0_1px_2px_rgba(28,26,23,.10)]",
        variant === "secondary" && "border border-line-strong bg-surface text-ink-soft hover:border-ink-faint hover:text-ink",
        variant === "ghost" && "text-ink-muted hover:bg-surface-sunk hover:text-ink",
        variant === "danger" && "bg-severe-fg text-white hover:opacity-90",
        className,
      )}
      {...props}
    />
  );
}

export function Field({ label, hint, className, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-[13px] font-medium text-ink-soft">{label}</span>
      <input
        className={cn(
          "h-10 w-full rounded-[10px] border border-line-strong bg-surface px-3 text-sm text-ink",
          "placeholder:text-ink-faint transition-[border-color,box-shadow] duration-150",
          "focus:border-teal-400 focus:outline-none focus:ring-4 focus:ring-teal-400/12",
          "tnum", className,
        )}
        {...props}
      />
      {hint && <span className="mt-1.5 block text-xs text-ink-faint">{hint}</span>}
    </label>
  );
}

const SEVERITY: Record<Severity, string> = {
  mild: "bg-mild-bg text-mild-fg",
  moderate: "bg-moderate-bg text-moderate-fg",
  severe: "bg-severe-bg text-severe-fg",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-md px-2 py-[3px] text-[11px] font-semibold uppercase tracking-[0.04em]",
      SEVERITY[severity],
    )}>
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
      {severity}
    </span>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "good" | "warn" }) {
  return (
    <span className={cn(
      "inline-flex items-center rounded-md px-2 py-[3px] text-[11px] font-semibold uppercase tracking-[0.04em]",
      tone === "neutral" && "bg-surface-sunk text-ink-muted",
      tone === "good" && "bg-good-bg text-good-fg",
      tone === "warn" && "bg-moderate-bg text-moderate-fg",
    )}>
      {children}
    </span>
  );
}

export function EmptyState({ icon, title, hint }: { icon?: ReactNode; title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      {icon && <div className="mb-3 text-ink-faint">{icon}</div>}
      <p className="text-sm font-medium text-ink-soft">{title}</p>
      {hint && <p className="mt-1.5 max-w-xs text-[13px] leading-relaxed text-ink-faint">{hint}</p>}
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2.5 px-5 py-10 text-[13px] text-ink-muted">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line-strong border-t-teal-500" />
      {label}
    </div>
  );
}

/** Three drifting dots — reads as "thinking" rather than "loading a page". */
export function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1" aria-label="Thinking">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-ink-faint"
          style={{ animationDelay: `${i * 0.18}s` }}
        />
      ))}
    </span>
  );
}

export function Stat({ label, value, unit, tone }: { label: string; value: ReactNode; unit?: string; tone?: "good" | "warn" | "bad" }) {
  return (
    <div className="px-5 py-4">
      <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-faint">{label}</p>
      <p className={cn(
        "mt-1.5 text-[26px] font-semibold leading-none tracking-[-0.02em] tnum",
        tone === "good" && "text-good-fg",
        tone === "warn" && "text-moderate-fg",
        tone === "bad" && "text-severe-fg",
        !tone && "text-ink",
      )}>
        {value}
        {unit && <span className="ml-1 text-[13px] font-normal tracking-normal text-ink-faint">{unit}</span>}
      </p>
    </div>
  );
}
