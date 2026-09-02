/**
 * Small presentational primitives.
 *
 * Hand-rolled rather than pulled from a component library: the set is small,
 * and owning it keeps the bundle and the design language under control.
 */
import type { ReactNode, ButtonHTMLAttributes, InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";
import type { Severity } from "@/lib/types";

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div className={cn("rounded-xl border border-ink-200 bg-white shadow-[0_1px_2px_rgba(19,27,40,.04)]", className)}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-ink-100 px-5 py-4">
      <div>
        <h2 className="text-[15px] font-semibold tracking-tight text-ink-900">{title}</h2>
        {subtitle && <p className="mt-0.5 text-[13px] text-ink-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
};

export function Button({ variant = "primary", size = "md", className, ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-500",
        "disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "px-2.5 py-1.5 text-[13px]" : "px-3.5 py-2 text-sm",
        variant === "primary" && "bg-accent-600 text-white hover:bg-accent-700",
        variant === "secondary" && "border border-ink-200 bg-white text-ink-700 hover:bg-ink-50",
        variant === "ghost" && "text-ink-600 hover:bg-ink-100",
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
      <span className="mb-1.5 block text-[13px] font-medium text-ink-700">{label}</span>
      <input
        className={cn(
          "w-full rounded-lg border border-ink-200 bg-white px-3 py-2 text-sm text-ink-900",
          "placeholder:text-ink-400 focus:border-accent-500 focus:outline-none",
          "focus:ring-2 focus:ring-accent-100 tnum",
          className,
        )}
        {...props}
      />
      {hint && <span className="mt-1 block text-xs text-ink-400">{hint}</span>}
    </label>
  );
}

const SEVERITY_STYLES: Record<Severity, string> = {
  mild: "bg-mild-bg text-mild-fg",
  moderate: "bg-moderate-bg text-moderate-fg",
  severe: "bg-severe-bg text-severe-fg",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className={cn("inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide", SEVERITY_STYLES[severity])}>
      {severity}
    </span>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "good" | "warn" }) {
  return (
    <span className={cn(
      "inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
      tone === "neutral" && "bg-ink-100 text-ink-600",
      tone === "good" && "bg-good-bg text-good-fg",
      tone === "warn" && "bg-moderate-bg text-moderate-fg",
    )}>
      {children}
    </span>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="px-5 py-12 text-center">
      <p className="text-sm font-medium text-ink-600">{title}</p>
      {hint && <p className="mt-1 text-[13px] text-ink-400">{hint}</p>}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 px-5 py-10 text-[13px] text-ink-400">
      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-ink-200 border-t-accent-500" />
      {label}
    </div>
  );
}

export function Stat({ label, value, unit, tone }: { label: string; value: ReactNode; unit?: string; tone?: "good" | "warn" | "bad" }) {
  return (
    <div className="px-5 py-4">
      <p className="text-[12px] font-medium uppercase tracking-wide text-ink-400">{label}</p>
      <p className={cn(
        "mt-1 text-2xl font-semibold tnum",
        tone === "good" && "text-good-fg",
        tone === "warn" && "text-moderate-fg",
        tone === "bad" && "text-severe-fg",
        !tone && "text-ink-900",
      )}>
        {value}
        {unit && <span className="ml-1 text-sm font-normal text-ink-400">{unit}</span>}
      </p>
    </div>
  );
}
