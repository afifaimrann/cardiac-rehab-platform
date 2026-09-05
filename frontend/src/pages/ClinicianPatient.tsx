import { useCallback, useEffect, useState } from "react";
import {
  ArrowLeft, CalendarDays, Footprints, MessageSquare, Sparkles, Stethoscope,
} from "lucide-react";
import { CONTENT, PageHeader } from "@/components/AppShell";
import { AssistantPanel } from "@/components/AssistantPanel";
import { StatusBadge } from "@/pages/Appointments";
import { MessagesPage } from "@/pages/Messages";
import { WalkTestPage } from "@/pages/WalkTest";
import {
  Button, Card, CardHeader, EmptyState, SeverityBadge, Spinner,
} from "@/components/exports";
import { api } from "@/lib/api";
import type {
  Appointment, CaseloadRow, Symptom, Vitals, WalkTest,
} from "@/lib/types";
import { cn, formatDateTime, formatTime, friendlyDay } from "@/lib/utils";

type Tab = "record" | "assistant" | "messages" | "walk" | "appointments";

const TABS: { key: Tab; label: string; icon: React.ReactNode }[] = [
  { key: "record", label: "Record", icon: <Stethoscope size={15} /> },
  { key: "assistant", label: "Assistant", icon: <Sparkles size={15} /> },
  { key: "messages", label: "Messages", icon: <MessageSquare size={15} /> },
  { key: "walk", label: "Walk test", icon: <Footprints size={15} /> },
  { key: "appointments", label: "Appointments", icon: <CalendarDays size={15} /> },
];

/**
 * One patient, everything about them.
 *
 * Tabbed rather than a single long scroll: a clinician opening a record before
 * a consultation is looking for one specific thing, and five sections stacked
 * vertically means scrolling past four of them every time.
 */
export function ClinicianPatientPage({ patient, onBack }: {
  patient: CaseloadRow;
  onBack: () => void;
}) {
  const [tab, setTab] = useState<Tab>("record");

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <PageHeader
        title={patient.full_name}
        subtitle={patient.primary_condition ?? "Cardiac rehabilitation"}
        action={<Button variant="secondary" onClick={onBack}><ArrowLeft size={15} /> Caseload</Button>}
      />

      <div className="border-b border-line bg-surface/40">
        <nav className={`${CONTENT} flex gap-1 overflow-x-auto`}>
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              aria-current={tab === t.key ? "page" : undefined}
              className={cn(
                "relative flex shrink-0 items-center gap-2 px-3.5 py-3 text-[13.5px] font-medium transition-colors duration-150",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/40",
                tab === t.key ? "text-teal-500" : "text-ink-muted hover:text-ink",
              )}
            >
              {t.icon} {t.label}
              {tab === t.key && (
                <span className="absolute inset-x-2 -bottom-px h-[2px] rounded-full bg-teal-500" />
              )}
            </button>
          ))}
        </nav>
      </div>

      <div className="flex-1 overflow-hidden">
        {tab === "record" && <RecordTab patient={patient} />}
        {tab === "assistant" && (
          <div className="h-full overflow-y-auto py-6">
            <div className={CONTENT}>
              <AssistantPanel patientId={patient.patient_id} patientName={patient.full_name} />
            </div>
          </div>
        )}
        {tab === "messages" && <MessagesPage patientId={patient.patient_id} />}
        {tab === "walk" && <WalkTestPage patientId={patient.patient_id} />}
        {tab === "appointments" && <AppointmentsTab patientId={patient.patient_id} />}
      </div>
    </div>
  );
}

function RecordTab({ patient }: { patient: CaseloadRow }) {
  const [vitals, setVitals] = useState<Vitals[] | null>(null);
  const [symptoms, setSymptoms] = useState<Symptom[]>([]);
  const [walks, setWalks] = useState<WalkTest[]>([]);

  useEffect(() => {
    let live = true;
    void Promise.all([
      api.clinician.patientVitals(patient.patient_id, 14),
      api.clinician.patientSymptoms(patient.patient_id, 10).catch(() => ({ items: [] })),
      api.walkTests.forPatient(patient.patient_id, 6).catch(() => []),
    ]).then(([v, s, w]) => {
      if (!live) return;
      setVitals(v.items);
      setSymptoms(s.items);
      setWalks(w);
    });
    return () => { live = false; };
  }, [patient.patient_id]);

  return (
    <div className="h-full overflow-y-auto py-6">
      <div className={`${CONTENT} space-y-5`}>
        <div className="grid gap-3 sm:grid-cols-3">
          <Summary label="Open flags"
            value={patient.open_flags === 0 ? "None" : String(patient.open_flags)}
            tone={patient.highest_open_severity ?? undefined} />
          <Summary label="Adherence"
            value={patient.adherence_pct == null ? "No plan" : `${patient.adherence_pct}%`} />
          <Summary label="Latest walk test"
            value={walks[0] ? `${walks[0].distance_m.toFixed(0)} m` : "None"} />
        </div>

        <Card>
          <CardHeader title="Readings" subtitle="Newest first" />
          {vitals === null ? <Spinner label="Loading readings" />
            : vitals.length === 0 ? <EmptyState title="No readings logged" /> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-line text-[11px] uppercase tracking-[0.05em] text-ink-faint">
                    <th className="px-5 py-2.5 text-start font-semibold">When</th>
                    <th className="px-5 py-2.5 text-start font-semibold">BP</th>
                    <th className="px-5 py-2.5 text-start font-semibold">HR</th>
                    <th className="px-5 py-2.5 text-start font-semibold">SpO₂</th>
                    <th className="px-5 py-2.5 text-start font-semibold">Weight</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {vitals.map((v) => (
                    <tr key={v.id} className="tnum">
                      <td className="px-5 py-2.5 text-ink-muted">{formatDateTime(v.recorded_at)}</td>
                      <td className="px-5 py-2.5 font-medium text-ink">
                        {v.systolic ? `${v.systolic}/${v.diastolic ?? "–"}` : "–"}
                      </td>
                      <td className="px-5 py-2.5 text-ink-soft">{v.heart_rate ?? "–"}</td>
                      <td className="px-5 py-2.5 text-ink-soft">{v.spo2 ? `${v.spo2}%` : "–"}</td>
                      <td className="px-5 py-2.5 text-ink-soft">{v.weight_kg ? `${v.weight_kg} kg` : "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {symptoms.length > 0 && (
          <Card>
            <CardHeader title="Reported symptoms" />
            <ul className="divide-y divide-line">
              {symptoms.map((s) => (
                <li key={s.id} className="flex items-start gap-3 px-5 py-3.5">
                  <SeverityBadge severity={s.severity} />
                  <div className="min-w-0">
                    <p className="text-[13.5px] leading-relaxed text-ink-soft">{s.description}</p>
                    <p className="mt-1 text-[12px] text-ink-faint">{formatDateTime(s.recorded_at)}</p>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        )}

        <div className="h-2" />
      </div>
    </div>
  );
}

function AppointmentsTab({ patientId }: { patientId: string }) {
  const [rows, setRows] = useState<Appointment[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setRows(await api.appointments.forPatient(patientId));
  }, [patientId]);

  useEffect(() => { void load(); }, [load]);

  async function mark(a: Appointment, status: "completed" | "no_show") {
    setBusy(a.id);
    try {
      await api.appointments.update(a.id, { status });
      await load();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="h-full overflow-y-auto py-6">
      <div className={`${CONTENT} space-y-5`}>
        <Card>
          <CardHeader title="Consultations" subtitle="Booked by the patient from your rota" />
          {rows === null ? <Spinner />
            : rows.length === 0 ? <EmptyState icon={<CalendarDays size={22} />}
                title="Nothing booked" hint="Publish availability from your diary and the patient can book it." />
            : (
            <ul className="divide-y divide-line">
              {rows.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5">
                  <div className="min-w-0">
                    <p className="text-[14px] font-medium text-ink">
                      {friendlyDay(a.starts_at)}, {formatTime(a.starts_at)}
                      <span className="ms-2 text-[12px] font-normal text-ink-faint">
                        {a.mode === "online" ? "video" : a.location ?? "in person"}
                      </span>
                    </p>
                    {a.reason && <p className="mt-1 text-[12.5px] text-ink-muted">{a.reason}</p>}
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={a.status} />
                    {a.status === "scheduled" && new Date(a.starts_at) < new Date() && (
                      <>
                        <Button variant="secondary" size="sm" disabled={busy === a.id}
                          onClick={() => void mark(a, "completed")}>Seen</Button>
                        <Button variant="ghost" size="sm" disabled={busy === a.id}
                          onClick={() => void mark(a, "no_show")}>Missed</Button>
                      </>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <div className="h-2" />
      </div>
    </div>
  );
}

function Summary({ label, value, tone }: {
  label: string; value: string; tone?: "mild" | "moderate" | "severe";
}) {
  return (
    <Card className={cn("px-5 py-4", tone === "severe" && "border-severe-fg/25 bg-severe-bg")}>
      <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-faint">{label}</p>
      <p className="mt-1.5 text-[24px] font-semibold leading-none tracking-[-0.02em] tnum text-ink">
        {value}
      </p>
    </Card>
  );
}
