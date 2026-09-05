import { CalendarDays, Footprints, MessageSquare, Video } from "lucide-react";
import { Card } from "@/components/exports";
import type { Appointment, WalkTest } from "@/lib/types";
import { cn, formatTime, friendlyDay } from "@/lib/utils";

/**
 * The strip across the top of the record: what is actually next.
 *
 * The overview below it answers "how am I doing". This answers "what do I do
 * now", which is the question a patient actually opens the app with, and it is
 * the only place the four modules meet — the appointment, the thread, the
 * walk test and the plan are otherwise four separate screens.
 */
export function UpNext({
  appointment, unread, lastWalkTest, onOpenAppointments, onOpenMessages, onOpenWalk,
}: {
  appointment: Appointment | null;
  unread: number;
  lastWalkTest: WalkTest | null;
  onOpenAppointments: () => void;
  onOpenMessages: () => void;
  onOpenWalk: () => void;
}) {
  const minutesAway = appointment
    ? (new Date(appointment.starts_at).getTime() - Date.now()) / 60000
    : null;
  const joinable = appointment?.mode === "online" && appointment.meeting_url
    && minutesAway != null && minutesAway < 15 && minutesAway > -60;

  const daysSinceWalk = lastWalkTest
    ? Math.floor((Date.now() - new Date(lastWalkTest.performed_at).getTime()) / 86_400_000)
    : null;

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      <Tile
        onClick={onOpenAppointments}
        icon={appointment?.mode === "online" ? <Video size={16} /> : <CalendarDays size={16} />}
        label="Next visit"
        highlight={Boolean(joinable)}
        value={appointment
          ? `${friendlyDay(appointment.starts_at)}, ${formatTime(appointment.starts_at)}`
          : "None booked"}
        hint={appointment
          ? joinable
            ? "Starting now — tap to join"
            : appointment.mode === "online"
              ? `Video with ${appointment.clinician_name ?? "your clinician"}`
              : appointment.location ?? "In person"
          : "Pick a time from your clinician's rota"}
      />

      <Tile
        onClick={onOpenMessages}
        icon={<MessageSquare size={16} />}
        label="Care team"
        highlight={unread > 0}
        value={unread > 0 ? `${unread} new message${unread === 1 ? "" : "s"}` : "No new messages"}
        hint={unread > 0 ? "Waiting for you to read" : "Ask a non-urgent question"}
      />

      <Tile
        onClick={onOpenWalk}
        icon={<Footprints size={16} />}
        label="Walk test"
        value={lastWalkTest ? `${lastWalkTest.distance_m.toFixed(0)} m` : "Not done yet"}
        hint={daysSinceWalk == null
          ? "Takes about ten minutes"
          : daysSinceWalk === 0 ? "Recorded today"
          : `${daysSinceWalk} day${daysSinceWalk === 1 ? "" : "s"} ago`}
      />
    </div>
  );
}

function Tile({ icon, label, value, hint, highlight, onClick }: {
  icon: React.ReactNode; label: string; value: string; hint: string;
  highlight?: boolean; onClick: () => void;
}) {
  return (
    <Card className={cn(
      "transition-[border-color,box-shadow,transform] duration-150",
      highlight && "border-teal-400/50 bg-teal-50/40",
    )}>
      <button
        type="button"
        onClick={onClick}
        className="flex w-full items-start gap-3 px-5 py-4 text-start focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/40 focus-visible:ring-inset rounded-[14px]"
      >
        <span className={cn(
          "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-[9px]",
          highlight ? "bg-teal-500 text-white" : "bg-surface-sunk text-ink-muted",
        )}>
          {icon}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-faint">
            {label}
          </span>
          <span className="mt-1 block truncate text-[15px] font-semibold tracking-[-0.01em] text-ink">
            {value}
          </span>
          <span className="mt-0.5 block text-[12px] leading-snug text-ink-muted line-clamp-2">
            {hint}
          </span>
        </span>
      </button>
    </Card>
  );
}
