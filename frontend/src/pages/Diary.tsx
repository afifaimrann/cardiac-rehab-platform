import { useCallback, useEffect, useState } from "react";
import { CalendarDays, MapPin, Plus, Trash2, Video } from "lucide-react";
import { CONTENT, PageHeader } from "@/components/AppShell";
import { StatusBadge } from "@/pages/Appointments";
import {
  Button, Card, CardHeader, EmptyState, Field, Spinner,
} from "@/components/exports";
import { api, ApiError } from "@/lib/api";
import type { Appointment, AvailabilityRule } from "@/lib/types";
import { cn, formatTime, friendlyDay, WEEKDAYS } from "@/lib/utils";

/**
 * The clinician's side of scheduling: publish a rota, read the diary.
 *
 * The rota is weekly rules rather than individual slots. A clinician who sees
 * patients on Tuesday afternoons says that once, not forty times, and changing
 * the rota does not mean editing rows that patients may already have booked.
 */
export function DiaryPage() {
  const [rules, setRules] = useState<AvailabilityRule[]>([]);
  const [diary, setDiary] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({
    weekday: 1, start_time: "09:00", end_time: "13:00",
    slot_minutes: 30, mode: "online" as "online" | "in_person", location: "",
  });

  const load = useCallback(async () => {
    const [r, d] = await Promise.all([
      api.appointments.availability(),
      api.appointments.diary(false),
    ]);
    setRules(r);
    setDiary(d);
    setLoading(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function addRule() {
    setError(null);
    try {
      await api.appointments.addAvailability({
        weekday: form.weekday,
        start_time: `${form.start_time}:00`,
        end_time: `${form.end_time}:00`,
        slot_minutes: form.slot_minutes,
        mode: form.mode,
        location: form.mode === "in_person" ? form.location || null : null,
      });
      setAdding(false);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not publish that window.");
    }
  }

  async function removeRule(id: string) {
    await api.appointments.removeAvailability(id);
    await load();
  }

  const upcoming = diary.filter(
    (a) => a.status === "scheduled" && new Date(a.starts_at) > new Date(),
  );

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <PageHeader
        title="Diary"
        subtitle="Publish when you are available; patients book themselves"
        action={<Button onClick={() => setAdding(!adding)}><Plus size={16} /> Add availability</Button>}
      />

      <div className="flex-1 overflow-y-auto py-6">
        <div className={`${CONTENT} grid items-start gap-5 xl:grid-cols-[1fr_380px]`}>
          <div className="min-w-0 space-y-5">
            <Card>
              <CardHeader
                title="Upcoming consultations"
                subtitle={upcoming.length ? `${upcoming.length} booked` : undefined}
              />
              {loading ? <Spinner />
                : upcoming.length === 0 ? (
                  <EmptyState icon={<CalendarDays size={22} />} title="Nothing booked yet"
                    hint="Publish an availability window and it appears to your patients straight away." />
                ) : (
                  <ul className="divide-y divide-line">
                    {upcoming.map((a) => (
                      <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5">
                        <div className="flex min-w-0 items-center gap-3.5">
                          <span className={cn(
                            "flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px]",
                            a.mode === "online" ? "bg-teal-50 text-teal-500" : "bg-surface-sunk text-ink-muted",
                          )}>
                            {a.mode === "online" ? <Video size={16} /> : <MapPin size={16} />}
                          </span>
                          <div className="min-w-0">
                            <p className="text-[14px] font-medium text-ink">
                              {a.patient_name ?? "Patient"}
                            </p>
                            <p className="mt-0.5 text-[12.5px] text-ink-muted">
                              {friendlyDay(a.starts_at)}, {formatTime(a.starts_at)}
                              {a.reason && <span className="text-ink-faint"> · {a.reason}</span>}
                            </p>
                          </div>
                        </div>
                        {a.mode === "online" && a.meeting_url && (
                          <Button variant="secondary" size="sm"
                            onClick={() => window.open(a.meeting_url!, "_blank", "noopener,noreferrer")}>
                            <Video size={14} /> Join
                          </Button>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
            </Card>

            {diary.length > upcoming.length && (
              <Card>
                <CardHeader title="Earlier" />
                <ul className="divide-y divide-line">
                  {diary.filter((a) => !upcoming.includes(a)).slice(0, 12).map((a) => (
                    <li key={a.id} className="flex items-center justify-between gap-3 px-5 py-3">
                      <p className="text-[13.5px] text-ink-soft">
                        {a.patient_name ?? "Patient"}
                        <span className="ms-2 text-[12px] text-ink-faint">
                          {friendlyDay(a.starts_at)}, {formatTime(a.starts_at)}
                        </span>
                      </p>
                      <StatusBadge status={a.status} />
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </div>

          <Card className="h-fit">
            <CardHeader title="Your weekly rota" subtitle="Every week, until you withdraw it" />

            {error && (
              <p role="alert" className="mx-5 mt-3 rounded-[10px] bg-severe-bg px-3 py-2 text-[13px] text-severe-fg">
                {error}
              </p>
            )}

            {adding && (
              <div className="space-y-3.5 border-b border-line bg-surface-sunk/40 px-5 py-4">
                <label className="block">
                  <span className="mb-1.5 block text-[13px] font-medium text-ink-soft">Day</span>
                  <select
                    value={form.weekday}
                    onChange={(e) => setForm({ ...form, weekday: Number(e.target.value) })}
                    className="h-10 w-full rounded-[10px] border border-line-strong bg-surface px-3 text-sm text-ink focus:border-teal-400 focus:outline-none"
                  >
                    {WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
                  </select>
                </label>

                <div className="grid grid-cols-2 gap-3">
                  <Field label="From" type="time" value={form.start_time}
                    onChange={(e) => setForm({ ...form, start_time: e.target.value })} />
                  <Field label="To" type="time" value={form.end_time}
                    onChange={(e) => setForm({ ...form, end_time: e.target.value })} />
                </div>

                <label className="block">
                  <span className="mb-1.5 block text-[13px] font-medium text-ink-soft">
                    Appointment length
                  </span>
                  <select
                    value={form.slot_minutes}
                    onChange={(e) => setForm({ ...form, slot_minutes: Number(e.target.value) })}
                    className="h-10 w-full rounded-[10px] border border-line-strong bg-surface px-3 text-sm text-ink focus:border-teal-400 focus:outline-none"
                  >
                    {[15, 20, 30, 45, 60].map((m) => <option key={m} value={m}>{m} minutes</option>)}
                  </select>
                </label>

                <div className="flex gap-2">
                  {(["online", "in_person"] as const).map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setForm({ ...form, mode: m })}
                      className={cn(
                        "h-9 flex-1 rounded-[9px] border text-[13px] font-medium transition-colors duration-150",
                        form.mode === m
                          ? "border-teal-400 bg-teal-50 text-teal-500"
                          : "border-line-strong bg-surface text-ink-soft hover:border-ink-faint",
                      )}
                    >
                      {m === "online" ? "Video" : "In person"}
                    </button>
                  ))}
                </div>

                {form.mode === "in_person" && (
                  <Field label="Where" value={form.location} placeholder="Clinic B, 2nd floor"
                    onChange={(e) => setForm({ ...form, location: e.target.value })} />
                )}

                <div className="flex gap-2 pt-1">
                  <Button className="flex-1" onClick={() => void addRule()}>Publish</Button>
                  <Button variant="ghost" onClick={() => setAdding(false)}>Cancel</Button>
                </div>
              </div>
            )}

            {rules.length === 0 && !adding ? (
              <EmptyState title="No availability published"
                hint="Until you add a window, patients cannot book with you." />
            ) : (
              <ul className="divide-y divide-line">
                {[...rules].sort((a, b) => a.weekday - b.weekday || a.start_time.localeCompare(b.start_time))
                  .map((r) => (
                  <li key={r.id} className="flex items-center justify-between gap-3 px-5 py-3">
                    <div className="min-w-0">
                      <p className="text-[13.5px] font-medium text-ink">
                        {WEEKDAYS[r.weekday]} {r.start_time.slice(0, 5)}–{r.end_time.slice(0, 5)}
                      </p>
                      <p className="mt-0.5 text-[12px] text-ink-faint">
                        {r.slot_minutes}-minute slots ·{" "}
                        {r.mode === "online" ? "video" : r.location ?? "in person"}
                      </p>
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => void removeRule(r.id)}
                      aria-label="Withdraw this window">
                      <Trash2 size={14} />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
