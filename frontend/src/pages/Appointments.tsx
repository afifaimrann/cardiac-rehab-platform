import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CalendarDays, CalendarX2, Check, MapPin, Video, X,
} from "lucide-react";
import { CONTENT, PageHeader } from "@/components/AppShell";
import {
  Badge, Button, Card, CardHeader, EmptyState, Spinner,
} from "@/components/exports";
import { api, ApiError } from "@/lib/api";
import type { Appointment, Slot } from "@/lib/types";
import { cn, formatTime, friendlyDay } from "@/lib/utils";

/**
 * Booking, from the patient's side.
 *
 * The design decision worth naming: the patient picks a time, not a request.
 * "Ask for an appointment and wait for a call back" is the workflow this
 * replaces, so anything that reintroduces a wait — a request queue, an
 * approval step — would defeat the point. What the clinician controls is the
 * rota; within it, the patient books and the room is created immediately.
 */
export function AppointmentsPage() {
  const [slots, setSlots] = useState<Slot[]>([]);
  const [mine, setMine] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  const load = useCallback(async () => {
    const [available, booked] = await Promise.all([
      api.appointments.slots(21),
      api.appointments.mine(),
    ]);
    setSlots(available);
    setMine(booked);
    setLoading(false);
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function book(slot: Slot) {
    setBusy(slot.starts_at);
    setError(null);
    try {
      await api.appointments.book({
        starts_at: slot.starts_at,
        reason: reason.trim() || undefined,
      });
      setReason("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not book that time.");
      // Whatever went wrong, the list of open times is now suspect.
      await load();
    } finally {
      setBusy(null);
    }
  }

  async function cancel(appointment: Appointment) {
    setBusy(appointment.id);
    try {
      await api.appointments.cancel(appointment.id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not cancel.");
    } finally {
      setBusy(null);
    }
  }

  const upcoming = mine.filter(
    (a) => a.status === "scheduled" && new Date(a.starts_at) > new Date(),
  );
  const past = mine.filter((a) => !upcoming.includes(a));

  // Grouped by day: a flat list of forty half-hour slots is a wall of times.
  const byDay = useMemo(() => {
    const groups = new Map<string, Slot[]>();
    for (const slot of slots) {
      const key = new Date(slot.starts_at).toDateString();
      groups.set(key, [...(groups.get(key) ?? []), slot]);
    }
    return [...groups.entries()];
  }, [slots]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <PageHeader
        title="Appointments"
        subtitle="Book a video or in-person consultation with your care team"
      />

      <div className="flex-1 overflow-y-auto py-6">
        <div className={`${CONTENT} space-y-6`}>
          {error && (
            <p role="alert" className="rounded-[10px] bg-severe-bg px-4 py-3 text-[13px] text-severe-fg">
              {error}
            </p>
          )}

          {loading ? <Spinner /> : (
            <>
              {upcoming.length > 0 && (
                <section className="space-y-3">
                  {upcoming.map((a) => (
                    <NextAppointment key={a.id} appointment={a}
                      busy={busy === a.id} onCancel={() => void cancel(a)} />
                  ))}
                </section>
              )}

              <Card>
                <CardHeader
                  title="Open times"
                  subtitle={slots.length
                    ? "Pick a time and it is booked straight away — no waiting for a call back."
                    : undefined}
                />
                {byDay.length === 0 ? (
                  <EmptyState
                    icon={<CalendarX2 size={24} />}
                    title="No open times right now"
                    hint="Your clinician has not published a rota for the next three weeks. Message your care team if you need to be seen."
                  />
                ) : (
                  <div className="space-y-5 px-5 py-5">
                    <label className="block">
                      <span className="mb-1.5 block text-[13px] font-medium text-ink-soft">
                        What would you like to discuss? <span className="text-ink-faint">(optional)</span>
                      </span>
                      <input
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        placeholder="More breathless than usual on stairs"
                        maxLength={300}
                        className="h-10 w-full rounded-[10px] border border-line-strong bg-surface px-3 text-sm text-ink placeholder:text-ink-faint focus:border-teal-400 focus:outline-none focus:ring-4 focus:ring-teal-400/12"
                      />
                    </label>

                    {byDay.map(([day, daySlots]) => (
                      <div key={day}>
                        <p className="mb-2 text-[12.5px] font-semibold text-ink-soft">
                          {friendlyDay(daySlots[0].starts_at)}
                          <span className="ms-2 font-normal text-ink-faint">
                            {daySlots[0].mode === "online" ? "video" : daySlots[0].location}
                          </span>
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {daySlots.map((slot) => (
                            <button
                              key={slot.starts_at}
                              type="button"
                              disabled={busy !== null}
                              onClick={() => void book(slot)}
                              className={cn(
                                "h-9 rounded-[9px] border border-line-strong bg-surface px-3.5 text-[13px] font-medium tnum text-ink-soft",
                                "transition-[border-color,background-color,color] duration-150",
                                "hover:border-teal-400 hover:bg-teal-50 hover:text-teal-500",
                                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/40",
                                "disabled:pointer-events-none disabled:opacity-45",
                                busy === slot.starts_at && "border-teal-400 bg-teal-50 text-teal-500",
                              )}
                            >
                              {formatTime(slot.starts_at)}
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>

              {past.length > 0 && (
                <Card>
                  <CardHeader title="Past and cancelled" />
                  <ul className="divide-y divide-line">
                    {past.map((a) => (
                      <li key={a.id} className="flex items-center justify-between gap-4 px-5 py-3.5">
                        <div className="min-w-0">
                          <p className="text-[13.5px] text-ink">
                            {friendlyDay(a.starts_at)}, {formatTime(a.starts_at)}
                            <span className="ms-2 text-[12px] text-ink-faint">
                              {a.mode === "online" ? "video" : "in person"}
                            </span>
                          </p>
                          {a.clinician_notes && (
                            <p className="mt-1 text-[12.5px] leading-relaxed text-ink-muted">
                              {a.clinician_notes}
                            </p>
                          )}
                        </div>
                        <StatusBadge status={a.status} />
                      </li>
                    ))}
                  </ul>
                </Card>
              )}
            </>
          )}

          <div className="h-2" />
        </div>
      </div>
    </div>
  );
}

/** The next appointment, given the weight it has in the patient's week. */
function NextAppointment({ appointment: a, busy, onCancel }: {
  appointment: Appointment; busy: boolean; onCancel: () => void;
}) {
  const minutesAway = (new Date(a.starts_at).getTime() - Date.now()) / 60000;
  // The link appears fifteen minutes before and stays through the hour after;
  // a "join" button available for a call three weeks away is noise.
  const joinable = a.mode === "online" && a.meeting_url
    && minutesAway < 15 && minutesAway > -60;

  return (
    <Card className={cn(joinable && "border-teal-400/50 bg-teal-50/40")}>
      <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
        <div className="flex min-w-0 items-center gap-4">
          <div className="flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-[11px] bg-teal-500 text-white">
            {a.mode === "online" ? <Video size={18} /> : <MapPin size={18} />}
          </div>
          <div className="min-w-0">
            <p className="text-[15px] font-semibold tracking-[-0.01em] text-ink">
              {friendlyDay(a.starts_at)}, {formatTime(a.starts_at)}
            </p>
            <p className="mt-0.5 text-[13px] text-ink-muted">
              {a.clinician_name ?? "Your clinician"}
              {" · "}
              {a.mode === "online" ? "video consultation" : a.location ?? "in person"}
            </p>
            {a.reason && (
              <p className="mt-1 text-[12.5px] text-ink-faint">About: {a.reason}</p>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {a.mode === "online" && a.meeting_url && (
            <Button
              onClick={() => window.open(a.meeting_url!, "_blank", "noopener,noreferrer")}
              variant={joinable ? "primary" : "secondary"}
            >
              <Video size={15} /> {joinable ? "Join now" : "Open link"}
            </Button>
          )}
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            <X size={15} /> Cancel
          </Button>
        </div>
      </div>
    </Card>
  );
}

export function StatusBadge({ status }: { status: Appointment["status"] }) {
  if (status === "completed") return <Badge tone="good"><Check size={12} /> Completed</Badge>;
  if (status === "cancelled") return <Badge>Cancelled</Badge>;
  if (status === "no_show") return <Badge tone="warn">Missed</Badge>;
  return <Badge tone="good"><CalendarDays size={12} /> Scheduled</Badge>;
}
