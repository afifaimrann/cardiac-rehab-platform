import { useCallback, useEffect, useState } from "react";
import { Sparkles, Users } from "lucide-react";
import { CONTENT, PageHeader } from "@/components/AppShell";
import { AssistantPanel } from "@/components/AssistantPanel";
import { Avatar, Card, EmptyState, SeverityBadge, Spinner } from "@/components/exports";
import { api } from "@/lib/api";
import type { CaseloadRow } from "@/lib/types";
import { cn, relativeTime } from "@/lib/utils";

/**
 * The assistant as a destination of its own.
 *
 * The same panel is reachable from inside a patient's record, but a clinician
 * who wants to ask about someone should not have to remember which patient's
 * record to open first. Here the patient is the thing you pick, and the
 * question is the thing you came to ask.
 */
export function ClinicianAssistantPage({ initialPatientId }: {
  initialPatientId?: string;
}) {
  const [caseload, setCaseload] = useState<CaseloadRow[]>([]);
  const [selected, setSelected] = useState<CaseloadRow | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const { patients } = await api.clinician.caseload(28);
    setCaseload(patients);
    setSelected(
      patients.find((p) => p.patient_id === initialPatientId) ?? patients[0] ?? null,
    );
    setLoading(false);
  }, [initialPatientId]);

  useEffect(() => { void load(); }, [load]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <PageHeader
        title="Assistant"
        subtitle="Ask about any patient on your caseload — it reads their record, not the internet"
      />

      <div className="flex-1 overflow-y-auto py-6">
        <div className={`${CONTENT} grid items-start gap-5 lg:grid-cols-[280px_1fr]`}>
          <Card className="h-fit">
            <p className="border-b border-line px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-faint">
              Ask about
            </p>
            {loading ? <Spinner /> : caseload.length === 0 ? (
              <EmptyState icon={<Users size={20} />} title="No patients assigned" />
            ) : (
              <ul className="max-h-[60vh] overflow-y-auto p-2">
                {caseload.map((p) => (
                  <li key={p.patient_id}>
                    <button
                      type="button"
                      onClick={() => setSelected(p)}
                      aria-current={selected?.patient_id === p.patient_id ? "true" : undefined}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-[10px] px-2.5 py-2.5 text-start transition-colors duration-150",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/40",
                        selected?.patient_id === p.patient_id
                          ? "bg-teal-50" : "hover:bg-surface-sunk/60",
                      )}
                    >
                      <Avatar name={p.full_name} size={34} />
                      <span className="min-w-0 flex-1">
                        <span className={cn(
                          "block truncate text-[13.5px] font-medium",
                          selected?.patient_id === p.patient_id ? "text-teal-500" : "text-ink",
                        )}>
                          {p.full_name}
                        </span>
                        <span className="mt-0.5 block truncate text-[11.5px] text-ink-faint">
                          {p.open_flags > 0
                            ? `${p.open_flags} open flag${p.open_flags === 1 ? "" : "s"}`
                            : `last reading ${relativeTime(p.last_vitals_at)}`}
                        </span>
                      </span>
                      {p.highest_open_severity === "severe" && (
                        <SeverityBadge severity="severe" />
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <div className="min-w-0">
            {selected ? (
              <AssistantPanel
                key={selected.patient_id}
                patientId={selected.patient_id}
                patientName={selected.full_name}
              />
            ) : !loading && (
              <Card>
                <EmptyState
                  icon={<Sparkles size={22} />}
                  title="Nobody to ask about yet"
                  hint="Once patients are assigned to you, the assistant can read their records."
                />
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
