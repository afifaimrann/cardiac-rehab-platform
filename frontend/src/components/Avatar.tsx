import { cn } from "@/lib/utils";

/**
 * A person, shown as their photograph or their initials.
 *
 * Initials are the default rather than a generic silhouette: in a caseload
 * list, a column of identical grey figures tells the reader nothing, while
 * initials are enough to find the row you meant.
 */
export function Avatar({ name, src, size = 40, className }: {
  name?: string | null;
  src?: string | null;
  size?: number;
  className?: string;
}) {
  const initials = (name ?? "")
    .split(" ").filter(Boolean).slice(0, 2)
    .map((w) => w[0]).join("").toUpperCase();

  return (
    <span
      className={cn(
        "relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full",
        "bg-surface-sunk font-semibold text-ink-soft ring-1 ring-line",
        className,
      )}
      style={{ width: size, height: size, fontSize: Math.max(11, size * 0.36) }}
      aria-hidden={!name}
    >
      {src
        ? <img src={src} alt={name ?? ""} className="h-full w-full object-cover" />
        : <span className="select-none tracking-[0.02em]">{initials || "?"}</span>}
    </span>
  );
}
