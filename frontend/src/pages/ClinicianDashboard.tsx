import { useCallback, useEffect, useState } from "react";
import { Check, ChevronRight, ShieldAlert } from "lucide-react";
import { Layout } from "@/components/Layout";
import { Badge, Button, Card, CardHeader, EmptyState, SeverityBadge, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { CaseloadRow, RiskFlag, Vitals } from "@/lib/types";
import { cn, formatDateTime, relativeTime } from "@/lib/utils";

export function ClinicianDashboard() {
  const [caseload, setCaseload] = useState<CaseloadRow[]>([]);
  const [flags, setFlags] = useState<RiskFlag[]>([]);
  const [selected, setSelected] = useState<CaseloadRow | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const [c, f] = await Promise.all([api.clinician.caseload(28), api.clinician.flags("open", 50)]);
    setCaseload(c.patients);
    setFlags(f.items);
    setLoading(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  const urgent = caseload.filter((p) => p.highest_open_severity === "severe").length;

  return (
    <Layout
      title="Caseload"
      subtitle={
        loading ? undefined
          : `${caseload.length} patients · ${flags.length} open flags${urgent ? ` · ${urgent} needing urgent review` : ""}`
      }
    >
      {loading ? <Spinner /> : (
        <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
          <div className="space-y-5">
            <Card>
              <CardHeader title="Patients" subtitle="Sorted by clinical urgency" />
              {caseload.length === 0 ? (
                <EmptyState title="No patients assigned" hint="An administrator assigns patients to your caseload." />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-ink-100 text-left text-[12px] uppercase tracking-wide text-ink-400">
                        <th className="px-5 py-2.5 font-medium">Patient</th>
                        <th className="px-5 py-2.5 font-medium">Flags</th>
                        <th className="px-5 py-2.5 font-medium">Adherence</th>
                        <th className="px-5 py-2.5 font-medium">Last reading</th>
                        <th className="px-5 py-2.5" />
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-ink-100">
                      {caseload.map((p) => (
                        <tr
                          key={p.patient_id}
                          onClick={() => setSelected(p)}
                          className={cn(
                            "cursor-pointer transition hover:bg-ink-50",
                            selected?.patient_id === p.patient_id && "bg-accent-50",
                          )}
                        >
                          <td className="px-5 py-3">
                            <p className="font-medium text-ink-900">{p.full_name}</p>
                            <p className="text-[12px] text-ink-400">{p.primary_condition ?? "No condition recorded"}</p>
                          </td>
                          <td className="px-5 py-3">
                            {p.open_flags === 0 ? (
                              <Badge tone="good">clear</Badge>
                            ) : (
                              <div className="flex items-center gap-1.5">
                                <span className="tnum text-[13px] font-semibold">{p.open_flags}</span>
                                {p.highest_open_severity && <SeverityBadge severity={p.highest_open_severity} />}
                              </div>
                            )}
                          </td>
                          <td className="px-5 py-3">
                            {p.adherence_pct == null ? (
                              <span className="text-[13px] text-ink-400">no plan</span>
                            ) : (
                              <AdherenceBar pct={p.adherence_pct} />
                            )}
                          </td>
                          <td className="px-5 py-3 text-[13px] text-ink-500">{relativeTime(p.last_vitals_at)}</td>
                          <td className="px-3 py-3 text-ink-300"><ChevronRight size={16} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            {selected && <PatientDetail patient={selected} onClose={() => setSelected(null)} />}
          </div>

          <FlagQueue flags={flags} onResolved={load} />
        </div>
      )}
    </Layout>
  );
}

function AdherenceBar({ pct }: { pct: number }) {
  const tone = pct >= 80 ? "bg-good-fg" : pct >= 50 ? "bg-moderate-fg" : "bg-severe-fg";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-ink-100">
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <span className="tnum text-[13px] text-ink-600">{pct}%</span>
    </div>
  );
}

function FlagQueue({ flags, onResolved }: { flags: RiskFlag[]; onResolved: () => void }) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function resolve(id: string) {
    setBusyId(id);
    setError(null);
    try {
      await api.clinician.resolveFlag(id, "resolved", "Reviewed by clinician.");
      onResolved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not resolve that flag.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <Card className="h-fit">
      <CardHeader
        title={<span className="flex items-center gap-2"><ShieldAlert size={16} className="text-moderate-fg" /> Review queue</span>}
        subtitle={`${flags.length} open`}
      />
      {error && <p role="alert" className="mx-5 mt-3 rounded-lg bg-severe-bg px-3 py-2 text-[13px] text-severe-fg">{error}</p>}
      {flags.length === 0 ? (
        <EmptyState title="Queue is clear" hint="New flags appear here as patients log data." />
      ) : (
        <ul className="max-h-[560px] divide-y divide-ink-100 overflow-y-auto">
          {flags.map((f) => (
            <li key={f.id} className="px-5 py-3.5">
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <SeverityBadge severity={f.severity} />
                <span className="text-[11px] text-ink-400">{relativeTime(f.created_at)}</span>
              </div>
              <p className="text-[13px] leading-snug text-ink-700">{f.message}</p>
              <div className="mt-2 flex items-center justify-between">
                <code className="rounded bg-ink-100 px-1.5 py-0.5 text-[11px] text-ink-500">{f.rule_code}</code>
                <Button variant="secondary" size="sm" disabled={busyId === f.id} onClick={() => resolve(f.id)}>
                  <Check size={14} /> {busyId === f.id ? "…" : "Resolve"}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function PatientDetail({ patient, onClose }: { patient: CaseloadRow; onClose: () => void }) {
  const [vitals, setVitals] = useState<Vitals[] | null>(null);

  useEffect(() => {
    setVitals(null);
    void api.clinician.patientVitals(patient.patient_id, 12).then((r) => setVitals(r.items));
  }, [patient.patient_id]);

  return (
    <Card>
      <CardHeader
        title={patient.full_name}
        subtitle={patient.primary_condition ?? undefined}
        action={<Button variant="ghost" size="sm" onClick={onClose}>Close</Button>}
      />
      {vitals === null ? <Spinner label="Loading readings" /> : vitals.length === 0 ? (
        <EmptyState title="No readings logged" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-ink-100 text-left text-[12px] uppercase tracking-wide text-ink-400">
                <th className="px-5 py-2.5 font-medium">When</th>
                <th className="px-5 py-2.5 font-medium">BP</th>
                <th className="px-5 py-2.5 font-medium">HR</th>
                <th className="px-5 py-2.5 font-medium">SpO₂</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-100">
              {vitals.map((v) => (
                <tr key={v.id} className="tnum">
                  <td className="px-5 py-2.5 text-ink-500">{formatDateTime(v.recorded_at)}</td>
                  <td className="px-5 py-2.5 font-medium">{v.systolic ? `${v.systolic}/${v.diastolic ?? "–"}` : "–"}</td>
                  <td className="px-5 py-2.5">{v.heart_rate ?? "–"}</td>
                  <td className="px-5 py-2.5">{v.spo2 ? `${v.spo2}%` : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
