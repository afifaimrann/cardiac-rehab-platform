import type { ReactNode } from "react";
import { CONTENT } from "@/components/AppShell";
import { Avatar } from "@/components/Avatar";
import { cn } from "@/lib/utils";
import type { PatientProfile, User } from "@/lib/types";

/**
 * Identity banner.
 *
 * A patient record opens with the person, not with their numbers: who they are,
 * what they are recovering from, where they are in the programme, and who is
 * responsible for them. Everything below is read in that context.
 *
 * The programme bar is the one piece of decoration that earns its place — a
 * patient six weeks into twelve is somewhere specific, and a number in a list
 * of facts does not convey that the way a filled bar does.
 */
export function PatientHeader({
  user, profile, weekOfProgramme, programmeWeeks = 12, clinicianName, action,
}: {
  user: User;
  profile: PatientProfile | null;
  weekOfProgramme?: number | null;
  programmeWeeks?: number;
  clinicianName?: string | null;
  action?: ReactNode;
}) {
  const age = profile?.date_of_birth ? yearsSince(profile.date_of_birth) : null;
  const progress = weekOfProgramme != null
    ? Math.min(weekOfProgramme / programmeWeeks, 1)
    : null;

  return (
    <header className="relative overflow-hidden border-b border-line bg-surface/50">
      {/* A single wash of the accent behind the name, fading out well before
          the facts below. Enough to make the record feel like a cover page
          rather than a table; not enough to tint anything clinical. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[132px] bg-gradient-to-b from-teal-50 to-transparent opacity-70"
      />

      <div className={`${CONTENT} relative flex flex-wrap items-start gap-5 py-6`}>
        <Avatar name={user.full_name} src={user.avatar_url} size={64}
          className="ring-2 ring-surface shadow-[0_2px_10px_-4px_rgba(28,26,23,.35)]" />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <h1 className="font-serif text-[28px] leading-none tracking-[-0.02em] text-ink">
              {user.full_name}
            </h1>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-good-bg px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.05em] text-good-fg">
              <span className="h-1.5 w-1.5 rounded-full bg-current" />
              Active
            </span>
          </div>

          <p className="mt-2 text-[14px] text-ink-soft">
            {profile?.primary_condition ?? "Cardiac rehabilitation"}
          </p>

          <dl className="mt-3.5 flex flex-wrap items-center gap-x-6 gap-y-2 text-[12.5px]">
            {age != null && <Fact label="Age" value={`${age}`} />}
            {profile?.height_cm != null && <Fact label="Height" value={`${profile.height_cm} cm`} />}
            {profile?.target_hr_max != null && (
              <Fact label="HR ceiling" value={`${profile.target_hr_max} bpm`} />
            )}
            {clinicianName && <Fact label="Care team" value={clinicianName} />}
          </dl>

          {progress != null && weekOfProgramme != null && (
            <div className="mt-4 max-w-[340px]">
              <div className="flex items-baseline justify-between text-[11.5px]">
                <span className="font-semibold uppercase tracking-[0.06em] text-ink-faint">
                  Programme
                </span>
                <span className="tnum text-ink-muted">
                  week {weekOfProgramme} of {programmeWeeks}
                </span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-sunk">
                <div
                  className="h-full rounded-full bg-teal-500 transition-[width] duration-700"
                  style={{ width: `${progress * 100}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {action && <div className="ms-auto pt-1">{action}</div>}
      </div>
    </header>
  );
}

function Fact({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className={cn("flex items-baseline gap-1.5", className)}>
      <dt className="text-ink-faint">{label}</dt>
      <dd className="font-medium text-ink-soft tnum">{value}</dd>
    </div>
  );
}

function yearsSince(isoDate: string): number {
  const born = new Date(isoDate);
  const now = new Date();
  let age = now.getFullYear() - born.getFullYear();
  const monthDiff = now.getMonth() - born.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && now.getDate() < born.getDate())) age -= 1;
  return age;
}
