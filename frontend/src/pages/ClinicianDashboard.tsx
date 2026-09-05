import { useCallback, useEffect, useState } from "react";
import { Check, ChevronRight, Inbox, ShieldAlert, Sparkles, Users } from "lucide-react";
import { Avatar } from "@/components/Avatar";
import { ClinicianPatientPage } from "@/pages/ClinicianPatient";
import { CONTENT, PageHeader } from "@/components/AppShell";
import {
  Badge, Button, Card, CardHeader, EmptyState, SeverityBadge, Spinner,
} from "@/components/exports";
import { api, ApiError } from "@/lib/api";
import type { CaseloadRow, RiskFlag } from "@/lib/types";
import { cn, relativeTime } from "@/lib/utils";

export function ClinicianDashboard({ onAskAbout }: {
  /** Jump straight to the assistant for one patient. */
  onAskAbout?: (patientId: string) => void;
}) {
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

  // Opening a patient replaces the caseload entirely. A record read before a
  // consultation deserves the whole window, not a panel under a table.
  if (selected) {
    return <ClinicianPatientPage patient={selected} onBack={() => { setSelected(null); void load(); }} />;
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <PageHeader
        title="Caseload"
        subtitle={loading ? undefined
          : `${caseload.length} patients · ${flags.length} open flags${urgent ? ` · ${urgent} needing urgent review` : ""}`}
      />

      <div className="flex-1 overflow-y-auto py-7">
        {loading ? <Spinner /> : (
          <div className={`${CONTENT} grid items-start gap-5 xl:grid-cols-[1fr_360px]`}>
            <div className="min-w-0 space-y-5">
              <Card>
                <CardHeader title="Patients" subtitle="Sorted by clinical urgency" />
                {caseload.length === 0 ? (
                  <EmptyState icon={<Users size={22} />} title="No patients assigned"
                    hint="An administrator assigns patients to your caseload." />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-line text-[11px] uppercase tracking-[0.05em] text-ink-faint">
                          <th className="px-5 py-2.5 text-start font-semibold">Patient</th>
                          <th className="px-5 py-2.5 text-start font-semibold">Flags</th>
                          <th className="px-5 py-2.5 text-start font-semibold">Adherence</th>
                          <th className="px-5 py-2.5 text-start font-semibold">Last reading</th>
                          <th className="px-5 py-2.5 text-start font-semibold">Assistant</th>
                          <th className="px-3 py-2.5" />
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-line">
                        {caseload.map((p) => (
                          <tr key={p.patient_id} onClick={() => setSelected(p)}
                            className="cursor-pointer transition-colors duration-150 hover:bg-surface-sunk/50">
                            <td className="px-5 py-3">
                              <div className="flex items-center gap-3">
                                <Avatar name={p.full_name} size={32} />
                                <div className="min-w-0">
                                  <p className="font-medium text-ink">{p.full_name}</p>
                                  <p className="mt-0.5 text-[12px] text-ink-faint">
                                    {p.primary_condition ?? "No condition recorded"}
                                  </p>
                                </div>
                              </div>
                            </td>
                            <td className="px-5 py-3">
                              {p.open_flags === 0 ? <Badge tone="good">clear</Badge> : (
                                <div className="flex items-center gap-2">
                                  <span className="tnum text-[13px] font-semibold text-ink">{p.open_flags}</span>
                                  {p.highest_open_severity && <SeverityBadge severity={p.highest_open_severity} />}
                                </div>
                              )}
                            </td>
                            <td className="px-5 py-3">
                              {p.adherence_pct == null
                                ? <span className="text-[13px] text-ink-faint">no plan</span>
                                : <AdherenceBar pct={p.adherence_pct} />}
                            </td>
                            <td className="px-5 py-3 text-[13px] text-ink-muted">{relativeTime(p.last_vitals_at)}</td>
                            <td className="px-5 py-3">
                              {/* Stops the row click: this is a different
                                  destination, not a shortcut to the same one. */}
                              <Button
                                variant="secondary" size="sm"
                                onClick={(e) => { e.stopPropagation(); onAskAbout?.(p.patient_id); }}
                              >
                                <Sparkles size={14} /> Ask
                              </Button>
                            </td>
                            <td className="px-3 py-3 text-ink-faint"><ChevronRight size={16} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

            </div>

            <FlagQueue flags={flags} onResolved={load} />
          </div>
        )}
      </div>
    </div>
  );
}

function AdherenceBar({ pct }: { pct: number }) {
  const tone = pct >= 80 ? "bg-good-fg" : pct >= 50 ? "bg-moderate-fg" : "bg-severe-fg";
  return (
    <div className="flex items-center gap-2.5">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-sunk">
        <div className={cn("h-full rounded-full transition-[width] duration-500", tone)}
          style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <span className="tnum text-[13px] text-ink-soft">{pct}%</span>
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
    <Card className="h-fit xl:sticky xl:top-0">
      <CardHeader
        title={<span className="flex items-center gap-2"><ShieldAlert size={16} className="text-moderate-fg" /> Review queue</span>}
        subtitle={`${flags.length} open`}
      />
      {error && <p role="alert" className="mx-5 mt-3 rounded-[10px] bg-severe-bg px-3 py-2 text-[13px] text-severe-fg">{error}</p>}
      {flags.length === 0 ? (
        <EmptyState icon={<Inbox size={22} />} title="Queue is clear"
          hint="New flags appear here as patients log data." />
      ) : (
        <ul className="max-h-[calc(100vh-220px)] divide-y divide-line overflow-y-auto">
          {flags.map((f) => (
            <li key={f.id} className="px-5 py-4">
              <div className="mb-2 flex items-center justify-between gap-2">
                <SeverityBadge severity={f.severity} />
                <span className="text-[11px] text-ink-faint">{relativeTime(f.created_at)}</span>
              </div>
              <p className="text-[13px] leading-relaxed text-ink-soft">{f.message}</p>
              <div className="mt-2.5 flex items-center justify-between gap-2">
                <code className="rounded bg-surface-sunk px-1.5 py-0.5 text-[11px] text-ink-muted">{f.rule_code}</code>
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
