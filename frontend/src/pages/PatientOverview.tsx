import { lazy, Suspense, useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import {
  AlertTriangle, CalendarDays, ChevronRight, ClipboardList, MessageCircle,
  Plus, Stethoscope, X,
} from "lucide-react";
import { CONTENT, type NavKey } from "@/components/AppShell";
import { PatientHeader } from "@/components/PatientHeader";
import { UpNext } from "@/components/UpNext";
import { Sparkline } from "@/components/Sparkline";
import { Timeline, buildTimeline } from "@/components/Timeline";
import {
  Badge, Button, Card, CardHeader, EmptyState, Field, SeverityBadge, Spinner,
} from "@/components/exports";
import { useAuth } from "@/context/auth";
import { api, ApiError } from "@/lib/api";
import type {
  Adherence, Appointment, ExerciseSession, Plan, RiskFlag, Symptom, Vitals,
  WalkTest,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const BpChart = lazy(() => import("@/components/BpChart"));

// Programme-relevant ranges, used to draw the healthy band behind each trend.
const BAND = { systolic: [90, 140] as [number, number], hr: [50, 100] as [number, number] };

export function PatientOverview({ onAsk, onNavigate }: {
  onAsk: () => void;
  onNavigate: (key: NavKey) => void;
}) {
  const { user, profile } = useAuth();
  const [vitals, setVitals] = useState<Vitals[]>([]);
  const [sessions, setSessions] = useState<ExerciseSession[]>([]);
  const [symptoms, setSymptoms] = useState<Symptom[]>([]);
  const [flags, setFlags] = useState<RiskFlag[]>([]);
  const [adherence, setAdherence] = useState<Adherence | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [unread, setUnread] = useState(0);
  const [walkTests, setWalkTests] = useState<WalkTest[]>([]);
  const [loading, setLoading] = useState(true);
  const [logging, setLogging] = useState(false);

  const load = useCallback(async () => {
    // One round of requests rather than a waterfall: the overview is the first
    // screen after sign-in, and each of these is independent.
    const [v, s, y, f, a, p, appts, msgs, walks] = await Promise.all([
      api.vitals.list(30),
      api.program.sessions(20),
      api.symptoms.list(20),
      api.flags.own(20),
      api.program.adherence(28),
      api.program.activePlan().catch(() => null),
      api.appointments.mine(true).catch(() => []),
      api.messages.unread().catch(() => ({ unread_count: 0 })),
      api.walkTests.list(5).catch(() => []),
    ]);
    setVitals(v.items);
    setSessions(s.items);
    setSymptoms(y.items);
    setFlags(f.items);
    setAdherence(a);
    setPlan(p);
    setAppointments(appts);
    setUnread(msgs.unread_count);
    setWalkTests(walks);
    setLoading(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const openFlags = flags.filter((f) => f.status === "open");
  const latest = vitals[0];
  const series = useMemo(() => [...vitals].reverse(), [vitals]);
  const chartData = series.map((v) => ({
    date: new Date(v.recorded_at).toLocaleDateString(undefined, { day: "numeric", month: "short" }),
    systolic: v.systolic,
    diastolic: v.diastolic,
  }));
  const timeline = useMemo(
    () => buildTimeline(vitals, sessions, symptoms, flags).slice(0, 14),
    [vitals, sessions, symptoms, flags],
  );

  const week = plan
    ? Math.max(1, Math.ceil((Date.now() - +new Date(plan.starts_on)) / 604_800_000))
    : null;

  if (loading) {
    return <div className="flex h-full items-center justify-center"><Spinner label="Loading your record" /></div>;
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {user && (
        <PatientHeader
          user={user}
          profile={profile}
          weekOfProgramme={week}
          action={
            <div className="flex gap-2">
              <Button variant="secondary" onClick={onAsk}>
                <MessageCircle size={16} /> Ask a question
              </Button>
              <Button onClick={() => setLogging(true)}>
                <Plus size={16} /> Log a reading
              </Button>
            </div>
          }
        />
      )}

      <div className="flex-1 overflow-y-auto py-6">
        <div className={`${CONTENT} space-y-5`}>
          <UpNext
            appointment={appointments[0] ?? null}
            unread={unread}
            lastWalkTest={walkTests[0] ?? null}
            onOpenAppointments={() => onNavigate("appointments")}
            onOpenMessages={() => onNavigate("messages")}
            onOpenWalk={() => onNavigate("walk")}
          />

          {/* Critical first: anything awaiting review is readable without a click. */}
          {openFlags.length > 0 && (
            <Card className="border-severe-fg/25 bg-severe-bg">
              <div className="flex gap-3 px-5 py-4">
                <AlertTriangle size={18} className="mt-0.5 shrink-0 text-severe-fg" />
                <div className="min-w-0 space-y-2">
                  <p className="text-[13px] font-semibold text-severe-fg">
                    {openFlags.length} item{openFlags.length > 1 ? "s" : ""} with your care team
                  </p>
                  {/* The badge sits in its own column rather than wrapping
                      inline: a long message otherwise drops to the next line
                      and the list stops reading as a list. */}
                  {openFlags.slice(0, 3).map((f) => (
                    <div key={f.id} className="flex items-start gap-2.5">
                      <span className="mt-px shrink-0"><SeverityBadge severity={f.severity} /></span>
                      <p className="min-w-0 text-[13px] leading-relaxed text-ink-soft">{f.message}</p>
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          )}

          <div className="grid items-start gap-5 xl:grid-cols-[300px_1fr]">
            {/* Left rail: the facts that do not change hour to hour. */}
            <div className="space-y-5">
              <Card>
                <CardHeader title={<span className="flex items-center gap-2"><ClipboardList size={15} /> Care plan</span>} />
                {plan ? (
                  <dl className="divide-y divide-line">
                    <Row label="Plan" value={plan.title} />
                    <Row label="Sessions" value={`${plan.sessions_per_week} per week`} />
                    <Row label="Duration" value={`${plan.minutes_per_session} min each`} />
                    {plan.target_exertion_max && (
                      <Row label="Max exertion" value={`${plan.target_exertion_max}/20 Borg`} />
                    )}
                    <Row label="Started" value={new Date(plan.starts_on).toLocaleDateString(undefined, { day: "numeric", month: "long" })} />
                  </dl>
                ) : <EmptyState title="No active plan" hint="Your clinician will prescribe one." />}
                {plan?.instructions && (
                  <p className="border-t border-line px-5 py-3.5 text-[12.5px] leading-relaxed text-ink-muted">
                    {plan.instructions}
                  </p>
                )}
              </Card>

              <Card>
                <CardHeader title={<span className="flex items-center gap-2"><CalendarDays size={15} /> This month</span>} />
                <div className="px-5 py-4">
                  <div className="flex items-end justify-between">
                    <div>
                      <p className="text-[30px] font-semibold leading-none tracking-[-0.025em] tnum text-ink">
                        {adherence?.sessions_completed ?? 0}
                        <span className="text-[15px] font-normal text-ink-faint"> / {adherence?.sessions_expected ?? 0}</span>
                      </p>
                      <p className="mt-1.5 text-[12px] text-ink-muted">sessions completed</p>
                    </div>
                    {adherence?.adherence_pct != null && (
                      <span className={cn(
                        "text-[15px] font-semibold tnum",
                        adherence.adherence_pct >= 80 ? "text-good-fg"
                          : adherence.adherence_pct >= 50 ? "text-moderate-fg" : "text-severe-fg",
                      )}>
                        {adherence.adherence_pct}%
                      </span>
                    )}
                  </div>
                  <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-sunk">
                    <div className={cn("h-full rounded-full transition-[width] duration-700",
                      (adherence?.adherence_pct ?? 0) >= 80 ? "bg-good-fg"
                        : (adherence?.adherence_pct ?? 0) >= 50 ? "bg-moderate-fg" : "bg-severe-fg")}
                      style={{ width: `${Math.min(adherence?.adherence_pct ?? 0, 100)}%` }} />
                  </div>
                  <p className="mt-3 text-[12px] text-ink-muted">
                    {adherence?.minutes_completed ?? 0} minutes over {adherence?.window_days ?? 28} days
                  </p>
                </div>
              </Card>

              <Card>
                <CardHeader title={<span className="flex items-center gap-2"><Stethoscope size={15} /> Your baseline</span>} />
                <dl className="divide-y divide-line">
                  <Row label="Resting HR" value={profile?.resting_hr_baseline ? `${profile.resting_hr_baseline} bpm` : "—"} />
                  <Row label="HR ceiling" value={profile?.target_hr_max ? `${profile.target_hr_max} bpm` : "—"} />
                  <Row label="Language" value={profile?.language === "bn" ? "বাংলা" : "English"} />
                </dl>
              </Card>
            </div>

            {/* Main column: measurements, then the record of what happened. */}
            <div className="min-w-0 space-y-5">
              <div className="grid gap-3 sm:grid-cols-3">
                <VitalTile
                  label="Blood pressure" unit="mmHg"
                  value={latest?.systolic ? `${latest.systolic}/${latest.diastolic ?? "–"}` : "—"}
                  values={series.map((v) => v.systolic)} band={BAND.systolic} min={70} max={200}
                  tone={latest?.systolic == null ? "normal"
                    : latest.systolic >= 180 ? "bad" : latest.systolic >= 160 ? "warn" : "normal"}
                />
                <VitalTile
                  label="Heart rate" unit="bpm"
                  value={latest?.heart_rate ?? "—"}
                  values={series.map((v) => v.heart_rate)} band={BAND.hr} min={40} max={140}
                  tone={latest?.heart_rate == null ? "normal"
                    : latest.heart_rate > (profile?.target_hr_max ?? 120) ? "warn" : "normal"}
                />
                <VitalTile
                  label="Weight" unit="kg"
                  value={latest?.weight_kg ?? "—"}
                  values={series.map((v) => v.weight_kg)} min={50} max={120}
                />
              </div>

              <Card>
                <CardHeader
                  title="Blood pressure over time"
                  subtitle={vitals.length ? `${vitals.length} readings` : undefined}
                  action={
                    <div className="flex items-center gap-3.5 pt-1 text-[11.5px] text-ink-muted">
                      <span className="inline-flex items-center gap-1.5">
                        <span className="h-[2px] w-4 rounded-full bg-accent-500" /> Systolic
                      </span>
                      <span className="inline-flex items-center gap-1.5">
                        <span className="h-0 w-4 border-t-2 border-dashed border-ink-faint" /> Diastolic
                      </span>
                    </div>
                  }
                />
                {chartData.length === 0
                  ? <EmptyState title="No readings yet" hint="Log your first reading to see the trend." />
                  : <Suspense fallback={<Spinner label="Loading chart" />}><BpChart data={chartData} /></Suspense>}
              </Card>

              <Card>
                <CardHeader title="Recent activity" subtitle="Readings, sessions, symptoms and flags in one place" />
                {timeline.length === 0
                  ? <EmptyState title="Nothing recorded yet" />
                  : <Timeline entries={timeline} />}
              </Card>
            </div>
          </div>

          <div className="h-2" />
        </div>
      </div>

      {logging && (
        <LogReadingDialog
          onClose={() => setLogging(false)}
          onSaved={() => { setLogging(false); void load(); }}
        />
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 px-5 py-2.5">
      <dt className="text-[12.5px] text-ink-muted">{label}</dt>
      <dd className="text-end text-[13px] font-medium text-ink">{value}</dd>
    </div>
  );
}

function VitalTile({ label, value, unit, values, band, min, max, tone = "normal" }: {
  label: string; value: React.ReactNode; unit: string;
  values: (number | null)[]; band?: [number, number]; min: number; max: number;
  tone?: "normal" | "warn" | "bad";
}) {
  return (
    <Card className="px-4 py-3.5">
      <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-faint">{label}</p>
      <div className="mt-2 flex items-end justify-between gap-2">
        <p className={cn(
          "text-[23px] font-semibold leading-none tracking-[-0.025em] tnum",
          tone === "bad" && "text-severe-fg",
          tone === "warn" && "text-moderate-fg",
          tone === "normal" && "text-ink",
        )}>
          {value}
          <span className="ms-1 text-[11.5px] font-normal tracking-normal text-ink-faint">{unit}</span>
        </p>
        <Sparkline values={values} min={min} max={max} band={band} tone={tone} />
      </div>
    </Card>
  );
}

/** Logging is an action, not the page. A dialog keeps the record in view. */
function LogReadingDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ systolic: "", diastolic: "", heart_rate: "", spo2: "", weight_kg: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [flags, setFlags] = useState<RiskFlag[]>([]);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const body = Object.fromEntries(
        Object.entries(form).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)]),
      );
      const res = await api.vitals.create(body);
      if (res.flags_raised.length) {
        // Hold the dialog open so the patient reads what was flagged.
        setFlags(res.flags_raised);
        setForm({ systolic: "", diastolic: "", heart_rate: "", spo2: "", weight_kg: "" });
      } else {
        onSaved();
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save that reading.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/25 p-4 backdrop-blur-[2px]"
      role="dialog" aria-modal="true" aria-label="Log a reading" onClick={onClose}>
      <div className="animate-rise w-full max-w-[420px]" onClick={(e) => e.stopPropagation()}>
        <Card>
          <CardHeader title="Log a reading" subtitle="Fill in whatever you measured"
            action={<Button variant="ghost" size="icon" onClick={onClose} aria-label="Close"><X size={17} /></Button>} />
          <form onSubmit={submit} className="space-y-3.5 px-5 py-4">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Systolic" inputMode="numeric" autoFocus value={form.systolic} onChange={set("systolic")} placeholder="120" />
              <Field label="Diastolic" inputMode="numeric" value={form.diastolic} onChange={set("diastolic")} placeholder="80" />
              <Field label="Heart rate" inputMode="numeric" value={form.heart_rate} onChange={set("heart_rate")} placeholder="72" />
              <Field label="SpO₂ %" inputMode="numeric" value={form.spo2} onChange={set("spo2")} placeholder="98" />
            </div>
            <Field label="Weight (kg)" inputMode="decimal" value={form.weight_kg} onChange={set("weight_kg")} placeholder="72.5" />

            {error && <p role="alert" className="rounded-[10px] bg-severe-bg px-3 py-2 text-[13px] text-severe-fg">{error}</p>}

            {flags.length > 0 && (
              <div className="space-y-2 rounded-[10px] border border-severe-fg/20 bg-severe-bg p-3">
                <p className="text-[12px] font-semibold text-severe-fg">Your care team has been notified</p>
                {flags.map((f) => (
                  <div key={f.id} className="flex items-start gap-2">
                    <SeverityBadge severity={f.severity} />
                    <p className="text-[13px] leading-snug text-ink-soft">{f.message}</p>
                  </div>
                ))}
              </div>
            )}

            <div className="flex gap-2">
              {flags.length > 0 ? (
                <Button type="button" className="w-full" onClick={onSaved}>
                  Understood <ChevronRight size={15} />
                </Button>
              ) : (
                <>
                  <Button type="button" variant="secondary" className="flex-1" onClick={onClose}>Cancel</Button>
                  <Button type="submit" disabled={busy} className="flex-1">
                    {busy ? "Saving…" : "Save reading"}
                  </Button>
                </>
              )}
            </div>
          </form>
          <div className="flex items-center justify-between gap-2 border-t border-line px-5 py-3">
            <p className="text-[12px] text-ink-muted">Checked against your plan automatically</p>
            <Badge>auto</Badge>
          </div>
        </Card>
      </div>
    </div>
  );
}
