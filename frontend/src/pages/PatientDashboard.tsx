import { lazy, Suspense, useCallback, useEffect, useState, type FormEvent } from "react";
import { Activity, AlertTriangle, Plus } from "lucide-react";

// Deferred so the charting library is fetched only when a chart is shown.
const BpChart = lazy(() => import("@/components/BpChart"));
import { Layout } from "@/components/Layout";
import { Badge, Button, Card, CardHeader, EmptyState, Field, SeverityBadge, Spinner, Stat } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Adherence, Plan, RiskFlag, Vitals } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

export function PatientDashboard() {
  const [vitals, setVitals] = useState<Vitals[]>([]);
  const [adherence, setAdherence] = useState<Adherence | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [recentFlags, setRecentFlags] = useState<RiskFlag[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const [v, a, p] = await Promise.all([
      api.vitals.list(30),
      api.program.adherence(28),
      api.program.activePlan().catch(() => null),
    ]);
    setVitals(v.items);
    setAdherence(a);
    setPlan(p);
    setLoading(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const latest = vitals[0];
  // Oldest-first for the chart; the API returns newest-first for the list.
  const chartData = [...vitals].reverse().map((v) => ({
    date: new Date(v.recorded_at).toLocaleDateString(undefined, { day: "numeric", month: "short" }),
    systolic: v.systolic,
    diastolic: v.diastolic,
  }));

  return (
    <Layout title="Your recovery" subtitle={plan ? plan.title : "No active plan yet"}>
      {loading ? <Spinner /> : (
        <div className="space-y-5">
          <Card>
            <div className="grid grid-cols-2 divide-x divide-ink-100 sm:grid-cols-4">
              <Stat label="Latest BP" unit="mmHg"
                value={latest?.systolic ? `${latest.systolic}/${latest.diastolic ?? "–"}` : "–"} />
              <Stat label="Heart rate" unit="bpm" value={latest?.heart_rate ?? "–"} />
              <Stat label="Adherence" unit="%"
                value={adherence?.adherence_pct ?? "–"}
                tone={
                  adherence?.adherence_pct == null ? undefined
                    : adherence.adherence_pct >= 80 ? "good"
                    : adherence.adherence_pct >= 50 ? "warn" : "bad"
                } />
              <Stat label="Sessions" unit={`of ${adherence?.sessions_expected ?? 0}`}
                value={adherence?.sessions_completed ?? 0} />
            </div>
          </Card>

          {recentFlags.length > 0 && (
            <Card className="border-severe-bg bg-severe-bg/40">
              <div className="flex gap-3 px-5 py-4">
                <AlertTriangle size={18} className="mt-0.5 shrink-0 text-severe-fg" />
                <div className="space-y-1.5">
                  <p className="text-[13px] font-semibold text-severe-fg">
                    Your care team has been notified
                  </p>
                  {recentFlags.map((f) => (
                    <p key={f.id} className="text-[13px] text-ink-700">{f.message}</p>
                  ))}
                </div>
              </div>
            </Card>
          )}

          <div className="grid gap-5 lg:grid-cols-[380px_1fr]">
            <LogVitalsCard onLogged={(flags) => { setRecentFlags(flags); void load(); }} />

            <Card>
              <CardHeader title="Blood pressure" subtitle="Last 30 readings" />
              {chartData.length === 0 ? (
                <EmptyState title="No readings yet" hint="Log your first reading to see the trend." />
              ) : (
                <Suspense fallback={<Spinner label="Loading chart" />}>
                  <BpChart data={chartData} />
                </Suspense>
              )}
            </Card>
          </div>

          <Card>
            <CardHeader title="Recent readings" subtitle={`${vitals.length} shown`} />
            {vitals.length === 0 ? (
              <EmptyState title="Nothing logged yet" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-ink-100 text-left text-[12px] uppercase tracking-wide text-ink-400">
                      <th className="px-5 py-2.5 font-medium">When</th>
                      <th className="px-5 py-2.5 font-medium">BP</th>
                      <th className="px-5 py-2.5 font-medium">HR</th>
                      <th className="px-5 py-2.5 font-medium">SpO₂</th>
                      <th className="px-5 py-2.5 font-medium">Weight</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-ink-100">
                    {vitals.slice(0, 10).map((v) => (
                      <tr key={v.id} className="tnum hover:bg-ink-50/60">
                        <td className="px-5 py-2.5 text-ink-500">{formatDateTime(v.recorded_at)}</td>
                        <td className="px-5 py-2.5 font-medium">
                          {v.systolic ? `${v.systolic}/${v.diastolic ?? "–"}` : "–"}
                        </td>
                        <td className="px-5 py-2.5">{v.heart_rate ?? "–"}</td>
                        <td className="px-5 py-2.5">{v.spo2 ? `${v.spo2}%` : "–"}</td>
                        <td className="px-5 py-2.5">{v.weight_kg ? `${v.weight_kg} kg` : "–"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}
    </Layout>
  );
}

function LogVitalsCard({ onLogged }: { onLogged: (flags: RiskFlag[]) => void }) {
  const [form, setForm] = useState({ systolic: "", diastolic: "", heart_rate: "", spo2: "", weight_kg: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [flags, setFlags] = useState<RiskFlag[]>([]);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm({ ...form, [k]: e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const body = Object.fromEntries(
        Object.entries(form).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)]),
      );
      const res = await api.vitals.create(body);
      setFlags(res.flags_raised);
      onLogged(res.flags_raised);
      setForm({ systolic: "", diastolic: "", heart_rate: "", spo2: "", weight_kg: "" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save that reading.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader title="Log a reading" subtitle="Fill in whatever you measured" />
      <form onSubmit={submit} className="space-y-3.5 px-5 py-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Systolic" inputMode="numeric" value={form.systolic} onChange={set("systolic")} placeholder="120" />
          <Field label="Diastolic" inputMode="numeric" value={form.diastolic} onChange={set("diastolic")} placeholder="80" />
          <Field label="Heart rate" inputMode="numeric" value={form.heart_rate} onChange={set("heart_rate")} placeholder="72" />
          <Field label="SpO₂ %" inputMode="numeric" value={form.spo2} onChange={set("spo2")} placeholder="98" />
        </div>
        <Field label="Weight (kg)" inputMode="decimal" value={form.weight_kg} onChange={set("weight_kg")} placeholder="72.5" />

        {error && (
          <p role="alert" className="rounded-lg bg-severe-bg px-3 py-2 text-[13px] text-severe-fg">{error}</p>
        )}

        {flags.length > 0 && (
          <div className="space-y-2 rounded-lg bg-ink-50 p-3">
            {flags.map((f) => (
              <div key={f.id} className="flex items-start gap-2">
                <SeverityBadge severity={f.severity} />
                <p className="text-[13px] leading-snug text-ink-700">{f.message}</p>
              </div>
            ))}
          </div>
        )}

        <Button type="submit" disabled={busy} className="w-full">
          <Plus size={15} /> {busy ? "Saving…" : "Save reading"}
        </Button>
      </form>
      <div className="flex items-center gap-2 border-t border-ink-100 px-5 py-3">
        <Activity size={14} className="text-ink-400" />
        <p className="text-[12px] text-ink-500">Readings are checked against your plan automatically.</p>
        <Badge>auto</Badge>
      </div>
    </Card>
  );
}
