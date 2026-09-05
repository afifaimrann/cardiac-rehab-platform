import type { ReactNode } from "react";
import { Activity, AlertTriangle, HeartPulse, MessageSquare } from "lucide-react";
import { cn, formatDateTime } from "@/lib/utils";
import type { ExerciseSession, RiskFlag, Symptom, Vitals } from "@/lib/types";

export interface TimelineEntry {
  id: string;
  at: string;
  kind: "vitals" | "session" | "symptom" | "flag";
  title: string;
  detail?: string;
  severity?: "mild" | "moderate" | "severe";
}

/**
 * One chronological record of what happened, rather than four separate lists.
 *
 * A clinician (and a patient) thinks in time: "the flag on Tuesday came right
 * after that session". Separate tables hide exactly that relationship.
 */
export function buildTimeline(
  vitals: Vitals[], sessions: ExerciseSession[], symptoms: Symptom[], flags: RiskFlag[],
): TimelineEntry[] {
  const entries: TimelineEntry[] = [
    ...vitals.map((v) => ({
      id: `v-${v.id}`, at: v.recorded_at, kind: "vitals" as const,
      title: v.systolic ? `Blood pressure ${v.systolic}/${v.diastolic ?? "–"}` : "Reading logged",
      detail: [
        v.heart_rate ? `${v.heart_rate} bpm` : null,
        v.spo2 ? `SpO₂ ${v.spo2}%` : null,
        v.weight_kg ? `${v.weight_kg} kg` : null,
      ].filter(Boolean).join(" · ") || undefined,
    })),
    ...sessions.map((s) => ({
      id: `s-${s.id}`, at: s.performed_at, kind: "session" as const,
      title: `${s.activity} · ${s.duration_minutes} min`,
      detail: [
        s.perceived_exertion ? `exertion ${s.perceived_exertion}/20` : null,
        s.completed ? null : "not completed",
      ].filter(Boolean).join(" · ") || undefined,
    })),
    ...symptoms.map((s) => ({
      id: `y-${s.id}`, at: s.recorded_at, kind: "symptom" as const,
      title: s.description, severity: s.severity,
    })),
    ...flags.map((f) => ({
      id: `f-${f.id}`, at: f.created_at, kind: "flag" as const,
      title: f.message, detail: f.status === "open" ? "Awaiting review" : "Reviewed",
      severity: f.severity,
    })),
  ];
  return entries.sort((a, b) => +new Date(b.at) - +new Date(a.at));
}

const ICONS: Record<TimelineEntry["kind"], ReactNode> = {
  vitals: <HeartPulse size={13} />,
  session: <Activity size={13} />,
  symptom: <MessageSquare size={13} />,
  flag: <AlertTriangle size={13} />,
};

export function Timeline({ entries }: { entries: TimelineEntry[] }) {
  return (
    <ol className="relative px-5 py-2">
      {/* One continuous rule behind the markers, so the eye reads a sequence. */}
      <span className="absolute inset-y-3 start-[30px] w-px bg-line" aria-hidden />
      {entries.map((e) => (
        <li key={e.id} className="relative flex gap-3.5 py-3">
          <span className={cn(
            "relative z-10 mt-0.5 flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full border",
            e.kind === "flag" && e.severity === "severe" && "border-severe-fg/30 bg-severe-bg text-severe-fg",
            e.kind === "flag" && e.severity !== "severe" && "border-moderate-fg/30 bg-moderate-bg text-moderate-fg",
            e.kind === "symptom" && "border-line-strong bg-surface text-ink-muted",
            e.kind === "session" && "border-line-strong bg-surface text-teal-500",
            e.kind === "vitals" && "border-line-strong bg-surface text-ink-muted",
          )}>
            {ICONS[e.kind]}
          </span>
          <div className="min-w-0 flex-1 pb-0.5">
            <p className="text-[13.5px] leading-snug text-ink">{e.title}</p>
            <p className="mt-1 text-[12px] text-ink-faint">
              {formatDateTime(e.at)}
              {e.detail && <span className="text-ink-muted"> · {e.detail}</span>}
            </p>
          </div>
        </li>
      ))}
    </ol>
  );
}
