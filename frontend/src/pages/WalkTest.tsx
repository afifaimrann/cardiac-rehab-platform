import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight, Ban, CheckCircle2, ChevronDown, Clock, Footprints, ShieldAlert,
  TrendingDown, TrendingUp,
} from "lucide-react";
import { CONTENT, PageHeader } from "@/components/AppShell";
import { BorgScale } from "@/components/BorgScale";
import { WalkTimer, type WalkResult } from "@/components/WalkTimer";
import {
  Badge, Button, Card, CardHeader, EmptyState, Field, SeverityBadge, Spinner,
} from "@/components/exports";
import { api, ApiError } from "@/lib/api";
import type {
  RiskFlag, Screening, WalkTest as WalkTestRecord, WalkTestPrefill, WalkTestResult,
} from "@/lib/types";
import { cn, formatDate } from "@/lib/utils";

type Stage = "history" | "screening" | "before" | "walking" | "after" | "result";

const COURSE_LENGTH = 30;

/** "12 minutes ago", for a value the user is being asked to confirm. */
function ago(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

const num = (v: string) => (v === "" ? undefined : Number(v));
const str = (v: number | null | undefined) => (v == null ? "" : String(v));

export function WalkTestPage({ patientId, embedded }: {
  patientId?: string;
  /** Inside the patient record's tabs: the tab strip already names the screen,
   *  so only the action belongs here, not a second title. */
  embedded?: boolean;
}) {
  const [stage, setStage] = useState<Stage>("history");
  const [history, setHistory] = useState<WalkTestRecord[]>([]);
  const [prefill, setPrefill] = useState<WalkTestPrefill | null>(null);
  const [loading, setLoading] = useState(true);

  const [screening, setScreening] = useState<Screening | null>(null);
  const [answers, setAnswers] = useState({
    resting_heart_rate: "", systolic: "", diastolic: "",
    acs_within_30_days: false, unstable_angina: false,
    syncope_history: false, acute_respiratory_failure: false,
  });
  // Collapsed by default when the previous test's answers are on file: the
  // common case is "nothing has changed", and four checkboxes a fortnight is
  // how a safety check becomes something people tick without reading.
  const [reviewingHistory, setReviewingHistory] = useState(false);

  const [before, setBefore] = useState({
    pre_heart_rate: "", pre_spo2: "", pre_systolic: "", pre_diastolic: "",
    pre_borg_dyspnoea: null as number | null, pre_borg_fatigue: null as number | null,
  });
  const [showBaselineBorg, setShowBaselineBorg] = useState(false);

  const [walk, setWalk] = useState<WalkResult | null>(null);
  const [after, setAfter] = useState({
    post_heart_rate: "", post_spo2: "", lowest_spo2: "",
    post_borg_dyspnoea: null as number | null, post_borg_fatigue: null as number | null,
    symptoms: "", stop_reason: "", weight_kg: "",
  });
  const [result, setResult] = useState<WalkTestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [items, hints] = await Promise.all([
      patientId ? api.walkTests.forPatient(patientId) : api.walkTests.list(),
      api.walkTests.prefill(patientId).catch(() => null),
    ]);
    setHistory(items);
    setPrefill(hints);
    setLoading(false);
  }, [patientId]);

  useEffect(() => { void load(); }, [load]);

  /** Open the screening stage with everything the record already knows. */
  function beginTest() {
    const v = prefill?.vitals;
    const prior = prefill?.previous_screening;
    setAnswers({
      // Only a current reading is offered. A resting heart rate from last week
      // is not a pre-test observation, and pre-filling it would let a stale
      // number clear a patient.
      resting_heart_rate: v && !v.stale ? str(v.heart_rate) : "",
      systolic: v && !v.stale ? str(v.systolic) : "",
      diastolic: v && !v.stale ? str(v.diastolic) : "",
      acs_within_30_days: prior?.acs_within_30_days ?? false,
      unstable_angina: prior?.unstable_angina ?? false,
      syncope_history: prior?.syncope_history ?? false,
      acute_respiratory_failure: prior?.acute_respiratory_failure ?? false,
    });
    setReviewingHistory(!prior);
    setScreening(null);
    setStage("screening");
  }

  async function runScreening() {
    setBusy(true);
    setError(null);
    try {
      const body: Record<string, unknown> = { ...answers };
      for (const k of ["resting_heart_rate", "systolic", "diastolic"] as const) {
        body[k] = answers[k] === "" ? null : Number(answers[k]);
      }
      const res = await api.walkTests.screen(body);
      setScreening(res);
      if (res.cleared) {
        // The screening observations are the baseline. Taking a heart rate and
        // a blood pressure twice, four fields apart, was asking the same
        // question in two different boxes.
        const v = prefill?.vitals;
        setBefore({
          pre_heart_rate: answers.resting_heart_rate,
          pre_systolic: answers.systolic,
          pre_diastolic: answers.diastolic,
          pre_spo2: v && !v.stale ? str(v.spo2) : "",
          pre_borg_dyspnoea: null, pre_borg_fatigue: null,
        });
        setStage("before");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not run the screening.");
    } finally {
      setBusy(false);
    }
  }

  async function save(stoppedEarly: boolean) {
    setBusy(true);
    setError(null);
    try {
      const logged = walk?.spo2Log ?? [];
      const body: Record<string, unknown> = {
        course_length_m: COURSE_LENGTH,
        laps: walk?.laps ?? 0,
        partial_lap_m: walk?.partial ?? 0,
        status: stoppedEarly ? "stopped_early" : "completed",
        stop_reason: stoppedEarly ? after.stop_reason || "stopped before six minutes" : undefined,
        pre_heart_rate: num(before.pre_heart_rate),
        pre_spo2: num(before.pre_spo2),
        pre_systolic: num(before.pre_systolic),
        pre_diastolic: num(before.pre_diastolic),
        pre_borg_dyspnoea: before.pre_borg_dyspnoea ?? undefined,
        pre_borg_fatigue: before.pre_borg_fatigue ?? undefined,
        post_heart_rate: num(after.post_heart_rate),
        // Typed value wins where there is one; otherwise the readings taken
        // during the walk stand in, which is what they were logged for.
        post_spo2: num(after.post_spo2) ?? logged.at(-1)?.value,
        lowest_spo2: num(after.lowest_spo2)
          ?? (logged.length ? Math.min(...logged.map((r) => r.value)) : undefined),
        post_borg_dyspnoea: after.post_borg_dyspnoea ?? undefined,
        post_borg_fatigue: after.post_borg_fatigue ?? undefined,
        rest_count: walk?.restCount ?? 0,
        rest_seconds: walk?.restSeconds ?? 0,
        symptoms: after.symptoms || undefined,
        // Whatever was on file unless it was retyped on the day.
        weight_kg: num(after.weight_kg) ?? prefill?.weight_kg ?? undefined,
        screen_acs_within_30_days: answers.acs_within_30_days,
        screen_unstable_angina: answers.unstable_angina,
        screen_syncope_history: answers.syncope_history,
        screen_acute_respiratory_failure: answers.acute_respiratory_failure,
      };
      const res = patientId
        ? await api.walkTests.createForPatient(patientId, body)
        : await api.walkTests.create(body);
      setResult(res);
      setStage("result");
      void load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save the test.");
    } finally {
      setBusy(false);
    }
  }

  function restart() {
    setStage("history");
    setScreening(null);
    setWalk(null);
    setResult(null);
    setError(null);
    setShowBaselineBorg(false);
    setAfter({ post_heart_rate: "", post_spo2: "", lowest_spo2: "",
      post_borg_dyspnoea: null, post_borg_fatigue: null,
      symptoms: "", stop_reason: "", weight_kg: "" });
  }

  const latest = history[0];
  const fresh = prefill?.vitals && !prefill.vitals.stale ? prefill.vitals : null;
  const prior = prefill?.previous_screening ?? null;
  const walkNadir = useMemo(() => {
    const log = walk?.spo2Log ?? [];
    return log.length ? Math.min(...log.map((r) => r.value)) : null;
  }, [walk]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {embedded ? (
        <div className="border-b border-line">
          <div className={`${CONTENT} flex items-center justify-between gap-4 py-3.5`}>
            <p className="text-[13px] text-ink-muted">
              Functional capacity, measured on a flat 30-metre course
            </p>
            {stage === "history"
              ? <Button onClick={beginTest}><Footprints size={16} /> Start a test</Button>
              : <Button variant="secondary" onClick={restart}>Cancel</Button>}
          </div>
        </div>
      ) : (
        <PageHeader
          title="Six-minute walk test"
          subtitle="Functional capacity, measured on a flat 30-metre course"
          action={stage === "history"
            ? <Button onClick={beginTest}><Footprints size={16} /> Start a test</Button>
            : <Button variant="secondary" onClick={restart}>Cancel</Button>}
        />
      )}

      <div className="flex-1 overflow-y-auto py-6">
        <div className={`${CONTENT} space-y-5`}>
          {error && (
            <p role="alert" className="rounded-[10px] bg-severe-bg px-4 py-3 text-[13px] text-severe-fg">
              {error}
            </p>
          )}

          {stage === "history" && (
            loading ? <Spinner /> : (
              <>
                {prefill && prefill.missing_for_prediction.length > 0 && history.length > 0 && (
                  <Card className="border-mild-fg/25 bg-mild-bg">
                    <p className="px-5 py-3.5 text-[13px] text-ink-soft">
                      Add {prefill.missing_for_prediction.join(", ")} in your profile and every
                      future test will also show how your distance compares with the predicted
                      distance for someone your age and build.
                    </p>
                  </Card>
                )}
                <History history={history} latest={latest} />
              </>
            )
          )}

          {stage === "screening" && (
            <Card className="mx-auto max-w-[620px]">
              <CardHeader
                title={<span className="flex items-center gap-2"><ShieldAlert size={16} /> Before you begin</span>}
                subtitle="Contraindication check. A test must not start if any of these apply."
              />
              <div className="space-y-5 px-5 py-5">
                <div>
                  <div className="grid grid-cols-3 gap-3">
                    <Field label="Resting HR" inputMode="numeric" value={answers.resting_heart_rate}
                      onChange={(e) => setAnswers({ ...answers, resting_heart_rate: e.target.value })} placeholder="72" />
                    <Field label="Systolic" inputMode="numeric" value={answers.systolic}
                      onChange={(e) => setAnswers({ ...answers, systolic: e.target.value })} placeholder="124" />
                    <Field label="Diastolic" inputMode="numeric" value={answers.diastolic}
                      onChange={(e) => setAnswers({ ...answers, diastolic: e.target.value })} placeholder="78" />
                  </div>
                  {fresh && (
                    <p className="mt-2 flex items-center gap-1.5 text-[12px] text-ink-faint">
                      <Clock size={12} />
                      From the reading logged {ago(fresh.recorded_at)}. Check it still holds.
                    </p>
                  )}
                  {prefill?.vitals?.stale && (
                    <p className="mt-2 flex items-center gap-1.5 text-[12px] text-ink-faint">
                      <Clock size={12} />
                      Last reading was {ago(prefill.vitals.recorded_at)} — take these now.
                    </p>
                  )}
                </div>

                {prior && !reviewingHistory ? (
                  <button
                    type="button"
                    onClick={() => setReviewingHistory(true)}
                    className="flex w-full items-center justify-between gap-3 rounded-[10px] border border-line bg-surface-sunk/50 px-4 py-3 text-start transition-colors duration-150 hover:border-line-strong"
                  >
                    <span className="text-[13px] leading-snug text-ink-soft">
                      {describeHistory(prior)}
                      <span className="block text-[12px] text-ink-faint">
                        Recorded at the test on {formatDate(prior.answered_at)}. Tap if anything has changed.
                      </span>
                    </span>
                    <ChevronDown size={16} className="shrink-0 text-ink-faint" />
                  </button>
                ) : (
                  <div className="space-y-2.5">
                    <Check label="Heart attack or unstable angina in the last 30 days"
                      checked={answers.acs_within_30_days}
                      onChange={(v) => setAnswers({ ...answers, acs_within_30_days: v })} />
                    <Check label="Unstable angina now"
                      checked={answers.unstable_angina}
                      onChange={(v) => setAnswers({ ...answers, unstable_angina: v })} />
                    <Check label="Any history of fainting (syncope)"
                      checked={answers.syncope_history}
                      onChange={(v) => setAnswers({ ...answers, syncope_history: v })} />
                    <Check label="Acute respiratory failure"
                      checked={answers.acute_respiratory_failure}
                      onChange={(v) => setAnswers({ ...answers, acute_respiratory_failure: v })} />
                  </div>
                )}

                {screening && !screening.cleared && (
                  <div className="rounded-[10px] border border-severe-fg/25 bg-severe-bg p-4">
                    <p className="flex items-center gap-2 text-[13px] font-semibold text-severe-fg">
                      <Ban size={15} /> This test must not go ahead
                    </p>
                    <ul className="mt-2 space-y-1">
                      {screening.absolute_blocks.map((b) => (
                        <li key={b} className="text-[13px] text-ink-soft">· {b}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {screening?.cleared && screening.relative_cautions.length > 0 && (
                  <div className="rounded-[10px] border border-moderate-fg/25 bg-moderate-bg p-4">
                    <p className="text-[13px] font-semibold text-moderate-fg">
                      Proceed only with clinician supervision
                    </p>
                    <ul className="mt-2 space-y-1">
                      {screening.relative_cautions.map((c) => (
                        <li key={c} className="text-[13px] text-ink-soft">· {c}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <Button className="w-full" disabled={busy} onClick={() => void runScreening()}>
                  {busy ? "Checking…" : "Check and continue"} <ArrowRight size={15} />
                </Button>
              </div>
            </Card>
          )}

          {stage === "before" && (
            <Card className="mx-auto max-w-[620px]">
              <CardHeader
                title="Baseline"
                subtitle="Carried over from the check you just did. Add the oxygen reading."
              />
              <div className="space-y-5 px-5 py-5">
                <div className="grid grid-cols-2 gap-3">
                  <Field label="SpO₂ %" inputMode="numeric" value={before.pre_spo2}
                    autoFocus
                    onChange={(e) => setBefore({ ...before, pre_spo2: e.target.value })} placeholder="98" />
                  <Field label="Heart rate" inputMode="numeric" value={before.pre_heart_rate}
                    onChange={(e) => setBefore({ ...before, pre_heart_rate: e.target.value })} placeholder="72" />
                  <Field label="Systolic" inputMode="numeric" value={before.pre_systolic}
                    onChange={(e) => setBefore({ ...before, pre_systolic: e.target.value })} placeholder="124" />
                  <Field label="Diastolic" inputMode="numeric" value={before.pre_diastolic}
                    onChange={(e) => setBefore({ ...before, pre_diastolic: e.target.value })} placeholder="78" />
                </div>

                {showBaselineBorg ? (
                  <div className="space-y-5">
                    <BorgScale label="Breathlessness before starting"
                      value={before.pre_borg_dyspnoea}
                      onChange={(v) => setBefore({ ...before, pre_borg_dyspnoea: v })} />
                    <BorgScale label="Fatigue before starting"
                      value={before.pre_borg_fatigue}
                      onChange={(v) => setBefore({ ...before, pre_borg_fatigue: v })} />
                  </div>
                ) : (
                  <button type="button" onClick={() => setShowBaselineBorg(true)}
                    className="text-[13px] text-accent-500 underline-offset-4 hover:underline">
                    Add baseline breathlessness and fatigue (optional)
                  </button>
                )}

                <Button className="w-full" onClick={() => setStage("walking")}>
                  Begin the walk <ArrowRight size={15} />
                </Button>
              </div>
            </Card>
          )}

          {stage === "walking" && (
            <Card className="mx-auto max-w-[420px]">
              <CardHeader title="Walking" subtitle={`${COURSE_LENGTH} m course · count each length`} />
              <div className="px-5 py-6">
                <WalkTimer courseLength={COURSE_LENGTH}
                  onFinish={(r) => { setWalk(r); setStage("after"); }} />
              </div>
            </Card>
          )}

          {stage === "after" && (
            <Card className="mx-auto max-w-[620px]">
              <CardHeader
                title="After the walk"
                subtitle={walk ? `${(walk.laps * COURSE_LENGTH + walk.partial).toFixed(0)} m in ${Math.floor(walk.seconds / 60)}:${String(walk.seconds % 60).padStart(2, "0")}` : undefined}
              />
              <div className="space-y-5 px-5 py-5">
                <div className="grid grid-cols-2 gap-3">
                  <Field label="Heart rate" inputMode="numeric" value={after.post_heart_rate}
                    autoFocus
                    onChange={(e) => setAfter({ ...after, post_heart_rate: e.target.value })} placeholder="104" />
                  <Field label="SpO₂ now" inputMode="numeric" value={after.post_spo2}
                    onChange={(e) => setAfter({ ...after, post_spo2: e.target.value })}
                    placeholder={walk?.spo2Log.at(-1)?.value?.toString() ?? "96"}
                    hint={walk?.spo2Log.length
                      ? `Last logged during the walk: ${walk.spo2Log.at(-1)?.value}%`
                      : undefined} />
                </div>

                {/* Everything measured during the walk is already in. Shown so
                    the person recording can see what will be saved, not so
                    they can type it again. */}
                <div className="rounded-[10px] border border-line bg-surface-sunk/50 px-4 py-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-faint">
                    Recorded during the walk
                  </p>
                  <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1.5 text-[13px] text-ink-soft">
                    <span>
                      Lowest SpO₂{" "}
                      <strong className={cn("tnum", walkNadir != null && walkNadir < 88 && "text-severe-fg")}>
                        {walkNadir != null ? `${walkNadir}%` : "not measured"}
                      </strong>
                    </span>
                    <span>Rests <strong className="tnum">{walk?.restCount ?? 0}</strong></span>
                    <span>Stopped for <strong className="tnum">{walk?.restSeconds ?? 0}s</strong></span>
                  </div>
                  {walkNadir == null && (
                    <label className="mt-3 block">
                      <span className="text-[12px] text-ink-muted">
                        Lowest SpO₂ observed, if you noted it
                      </span>
                      <input
                        type="number" min={50} max={100} value={after.lowest_spo2}
                        onChange={(e) => setAfter({ ...after, lowest_spo2: e.target.value })}
                        placeholder="93"
                        className="mt-1 h-9 w-full rounded-[9px] border border-line-strong bg-surface px-3 text-sm tnum text-ink focus:border-accent-400 focus:outline-none focus:ring-4 focus:ring-accent-400/12"
                      />
                    </label>
                  )}
                </div>

                <BorgScale label="Breathlessness at the end"
                  value={after.post_borg_dyspnoea}
                  onChange={(v) => setAfter({ ...after, post_borg_dyspnoea: v })} />
                <BorgScale label="Fatigue at the end"
                  value={after.post_borg_fatigue}
                  onChange={(v) => setAfter({ ...after, post_borg_fatigue: v })} />

                <Field label="Symptoms during or after" value={after.symptoms}
                  onChange={(e) => setAfter({ ...after, symptoms: e.target.value })}
                  placeholder="Chest pain, leg discomfort, dizziness…" />

                {prefill?.weight_kg != null ? (
                  <p className="text-[12.5px] text-ink-faint">
                    Using your recorded weight of {prefill.weight_kg} kg for the predicted
                    distance{prefill.weight_recorded_at ? ` (logged ${ago(prefill.weight_recorded_at)})` : ""}.{" "}
                    <button type="button"
                      onClick={() => setAfter({ ...after, weight_kg: String(prefill.weight_kg) })}
                      className="text-accent-500 underline-offset-4 hover:underline">
                      Weighed today?
                    </button>
                  </p>
                ) : (
                  <Field label="Weight (kg)" inputMode="decimal" value={after.weight_kg}
                    onChange={(e) => setAfter({ ...after, weight_kg: e.target.value })}
                    placeholder="72.5" hint="Needed once, for the predicted distance" />
                )}
                {after.weight_kg !== "" && prefill?.weight_kg != null && (
                  <Field label="Weight today (kg)" inputMode="decimal" value={after.weight_kg}
                    onChange={(e) => setAfter({ ...after, weight_kg: e.target.value })} />
                )}

                <div className="flex gap-2">
                  <Button variant="secondary" className="flex-1" disabled={busy}
                    onClick={() => void save(true)}>
                    Stopped early
                  </Button>
                  <Button className="flex-1" disabled={busy} onClick={() => void save(false)}>
                    {busy ? "Saving…" : "Save result"}
                  </Button>
                </div>
              </div>
            </Card>
          )}

          {stage === "result" && result && (
            <Result result={result} onDone={restart} />
          )}

          <div className="h-2" />
        </div>
      </div>
    </div>
  );
}

/** One sentence summarising the last screening, so a clinician can confirm at a
 *  glance instead of re-reading four questions. */
function describeHistory(prior: {
  acs_within_30_days: boolean; unstable_angina: boolean;
  syncope_history: boolean; acute_respiratory_failure: boolean;
}): string {
  const flagged = [
    prior.acs_within_30_days && "a recent cardiac event",
    prior.unstable_angina && "unstable angina",
    prior.syncope_history && "a history of fainting",
    prior.acute_respiratory_failure && "acute respiratory failure",
  ].filter(Boolean) as string[];

  return flagged.length === 0
    ? "Last time, none of the contraindications applied."
    : `Last time you reported ${flagged.join(", ")}.`;
}

function Check({ label, checked, onChange }: {
  label: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <label className={cn(
      "flex cursor-pointer items-start gap-3 rounded-[10px] border p-3 transition-colors duration-150",
      checked ? "border-severe-fg/30 bg-severe-bg" : "border-line hover:border-line-strong",
    )}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 accent-[var(--color-severe-fg)]" />
      <span className="text-[13.5px] leading-snug text-ink-soft">{label}</span>
    </label>
  );
}

function Result({ result, onDone }: { result: WalkTestResult; onDone: () => void }) {
  const t = result.walk_test;
  const change = result.change;

  return (
    <div className="mx-auto max-w-[620px] space-y-4">
      <Card>
        <div className="px-6 py-7 text-center">
          <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-faint">
            Distance walked
          </p>
          <p className="mt-2 text-[52px] font-semibold leading-none tracking-[-0.03em] tnum text-ink">
            {t.distance_m.toFixed(0)}
            <span className="ms-2 text-[20px] font-normal text-ink-faint">m</span>
          </p>

          {t.percent_predicted != null && (
            <p className="mt-3 text-[14px] text-ink-muted">
              {t.percent_predicted}% of predicted
              <span className="text-ink-faint"> ({t.predicted_distance_m?.toFixed(0)} m)</span>
            </p>
          )}

          {change && (
            <div className={cn(
              "mt-4 inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-[13px] font-medium",
              change.direction === "improved" ? "bg-good-bg text-good-fg"
                : change.direction === "declined" ? "bg-severe-bg text-severe-fg"
                : "bg-surface-sunk text-ink-muted",
            )}>
              {change.direction === "improved" ? <TrendingUp size={15} /> : <TrendingDown size={15} />}
              {Math.abs(change.change_m).toFixed(0)} m {change.direction} since {formatDate(change.previous_performed_at)}
              {change.clinically_meaningful && <Badge tone="warn">meaningful</Badge>}
            </div>
          )}

          {t.below_lower_limit && (
            <p className="mt-4 text-[13px] text-moderate-fg">
              Below the lower limit of normal for this patient.
            </p>
          )}
        </div>
      </Card>

      {result.flags_raised.length > 0 && (
        <Card className="border-severe-fg/25 bg-severe-bg">
          <div className="space-y-2.5 px-5 py-4">
            <p className="text-[13px] font-semibold text-severe-fg">Raised for clinical review</p>
            {result.flags_raised.map((f: RiskFlag) => (
              <div key={f.id} className="flex items-start gap-2">
                <SeverityBadge severity={f.severity} />
                <p className="text-[13px] leading-relaxed text-ink-soft">{f.message}</p>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card>
        <CardHeader title="Recorded" />
        <dl className="divide-y divide-line">
          <Row label="Heart rate" value={`${t.pre_heart_rate ?? "–"} → ${t.post_heart_rate ?? "–"} bpm`} />
          <Row label="SpO₂" value={`${t.pre_spo2 ?? "–"} → ${t.post_spo2 ?? "–"}%${t.lowest_spo2 ? ` (lowest ${t.lowest_spo2}%)` : ""}`} />
          <Row label="Breathlessness" value={`${t.pre_borg_dyspnoea ?? "–"} → ${t.post_borg_dyspnoea ?? "–"} / 10`} />
          <Row label="Fatigue" value={`${t.pre_borg_fatigue ?? "–"} → ${t.post_borg_fatigue ?? "–"} / 10`} />
          <Row label="Rests" value={t.rest_count ? `${t.rest_count} (${t.rest_seconds}s)` : "none"} />
          {t.symptoms && <Row label="Symptoms" value={t.symptoms} />}
          {t.stop_reason && <Row label="Stopped early" value={t.stop_reason} />}
        </dl>
      </Card>

      <Button className="w-full" onClick={onDone}>
        <CheckCircle2 size={16} /> Done
      </Button>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 px-5 py-3">
      <dt className="text-[12.5px] text-ink-muted">{label}</dt>
      <dd className="text-end text-[13px] font-medium tnum text-ink">{value}</dd>
    </div>
  );
}

function History({ history, latest }: { history: WalkTestRecord[]; latest?: WalkTestRecord }) {
  if (history.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={<Footprints size={24} />}
          title="No walk tests recorded"
          hint="The six-minute walk test measures how far you can walk on the flat in six minutes. It is the standard way to track functional capacity through rehabilitation."
        />
      </Card>
    );
  }

  const best = Math.max(...history.map((t) => t.distance_m));
  const max = Math.max(best, ...history.map((t) => t.predicted_distance_m ?? 0));

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-3">
        <Card className="px-5 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-faint">Latest</p>
          <p className="mt-2 text-[26px] font-semibold leading-none tnum text-ink">
            {latest?.distance_m.toFixed(0)}<span className="ms-1 text-[13px] font-normal text-ink-faint">m</span>
          </p>
          <p className="mt-2 text-[12px] text-ink-muted">{latest && formatDate(latest.performed_at)}</p>
        </Card>
        <Card className="px-5 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-faint">Best</p>
          <p className="mt-2 text-[26px] font-semibold leading-none tnum text-ink">
            {best.toFixed(0)}<span className="ms-1 text-[13px] font-normal text-ink-faint">m</span>
          </p>
          <p className="mt-2 text-[12px] text-ink-muted">
            {/* The protocol treats the longest distance as the true result,
                because repeated testing shows a learning effect. */}
            longest recorded
          </p>
        </Card>
        <Card className="px-5 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-faint">% predicted</p>
          <p className="mt-2 text-[26px] font-semibold leading-none tnum text-ink">
            {latest?.percent_predicted != null ? `${latest.percent_predicted}` : "—"}
            {latest?.percent_predicted != null && <span className="ms-1 text-[13px] font-normal text-ink-faint">%</span>}
          </p>
          <p className="mt-2 text-[12px] text-ink-muted">
            {latest?.predicted_distance_m ? `of ${latest.predicted_distance_m.toFixed(0)} m` : "height and weight needed"}
          </p>
        </Card>
      </div>

      <Card>
        <CardHeader title="Test history" subtitle="Longest distance is treated as the true result" />
        <ul className="divide-y divide-line">
          {history.map((t) => (
            <li key={t.id} className="px-5 py-3.5">
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0">
                  <p className="text-[14px] font-medium tnum text-ink">
                    {t.distance_m.toFixed(0)} m
                    {t.status === "stopped_early" && (
                      <span className="ms-2 text-[12px] font-normal text-moderate-fg">stopped early</span>
                    )}
                  </p>
                  <p className="mt-1 text-[12px] text-ink-faint">
                    {formatDate(t.performed_at)}
                    {t.lowest_spo2 != null && <span> · lowest SpO₂ {t.lowest_spo2}%</span>}
                    {t.post_borg_dyspnoea != null && <span> · breathlessness {t.post_borg_dyspnoea}/10</span>}
                  </p>
                </div>
                <div className="flex w-[42%] items-center gap-2">
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-sunk">
                    <div className={cn("h-full rounded-full",
                      t.below_lower_limit ? "bg-moderate-fg" : "bg-accent-500")}
                      style={{ width: `${(t.distance_m / max) * 100}%` }} />
                  </div>
                  {t.percent_predicted != null && (
                    <span className="w-11 text-end text-[12px] tnum text-ink-muted">{t.percent_predicted}%</span>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
