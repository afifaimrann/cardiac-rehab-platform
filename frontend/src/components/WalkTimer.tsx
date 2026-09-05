import { useEffect, useRef, useState } from "react";
import { Activity, Minus, Pause, Play, RotateCcw, Square } from "lucide-react";
import { Button } from "@/components/exports";
import { cn } from "@/lib/utils";

const TOTAL_SECONDS = 360;
// The protocol asks that the patient be told the time remaining each minute
// and encouraged to continue.
const PROMPTS: Record<number, string> = {
  300: "You are doing well. Five minutes to go.",
  240: "Keep up the good work. Four minutes to go.",
  180: "You are doing well. You are halfway.",
  120: "Keep up the good work. Two minutes to go.",
  60: "You are doing well. One minute to go.",
  15: "In a moment, I am going to tell you to stop. Keep walking until then.",
  0: "Stop where you are.",
};

export interface WalkResult {
  seconds: number;
  laps: number;
  partial: number;
  /** How many separate times the patient stopped, and for how long in total. */
  restCount: number;
  restSeconds: number;
  /** Every SpO2 reading taken during the walk, with when it was taken. */
  spo2Log: { second: number; value: number }[];
}

/**
 * The six-minute clock, with lap counting, rest tracking and oxygen readings.
 *
 * Everything measurable is measured here rather than asked for afterwards.
 * Rests and the SpO2 nadir used to be typed into a form once the patient had
 * sat down, from memory, by the person who had spent six minutes watching them
 * walk. Both are now a button.
 *
 * Timing is derived from a wall-clock start rather than counted in an interval,
 * because setInterval drifts and a background tab throttles it — a "six-minute"
 * walk that actually ran 5:47 invalidates the result.
 */
export function WalkTimer({ courseLength, onFinish }: {
  courseLength: number;
  onFinish: (result: WalkResult) => void;
}) {
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [laps, setLaps] = useState(0);
  const [partial, setPartial] = useState(0);
  const [prompt, setPrompt] = useState<string | null>(null);

  const [resting, setResting] = useState(false);
  const [restCount, setRestCount] = useState(0);
  const [restSeconds, setRestSeconds] = useState(0);
  const [spo2Log, setSpo2Log] = useState<{ second: number; value: number }[]>([]);
  const [spo2Draft, setSpo2Draft] = useState("");

  const startedAt = useRef<number | null>(null);
  const accumulated = useRef(0);
  const lastPrompt = useRef<number | null>(null);
  const restStartedAt = useRef<number | null>(null);

  useEffect(() => {
    if (!running) return;
    startedAt.current = Date.now();
    const tick = () => {
      const total = accumulated.current + (Date.now() - (startedAt.current ?? Date.now())) / 1000;
      const capped = Math.min(total, TOTAL_SECONDS);
      setElapsed(capped);

      const remaining = Math.round(TOTAL_SECONDS - capped);
      if (PROMPTS[remaining] && lastPrompt.current !== remaining) {
        lastPrompt.current = remaining;
        setPrompt(PROMPTS[remaining]);
      }
      if (capped >= TOTAL_SECONDS) {
        setRunning(false);
        accumulated.current = TOTAL_SECONDS;
      }
    };
    const id = window.setInterval(tick, 200);
    return () => {
      window.clearInterval(id);
      accumulated.current += (Date.now() - (startedAt.current ?? Date.now())) / 1000;
    };
  }, [running]);

  // A rest does not stop the clock. The six minutes run whether the patient is
  // walking or leaning on a wall, and pausing the timer would turn a poor
  // result into a good one.
  function toggleRest() {
    if (resting) {
      const seconds = (Date.now() - (restStartedAt.current ?? Date.now())) / 1000;
      setRestSeconds((s) => Math.round(s + seconds));
      restStartedAt.current = null;
      setResting(false);
    } else {
      restStartedAt.current = Date.now();
      setRestCount((n) => n + 1);
      setResting(true);
    }
  }

  const spo2Valid = (() => {
    const value = Number(spo2Draft);
    return spo2Draft !== "" && Number.isFinite(value) && value >= 50 && value <= 100;
  })();

  function logSpo2() {
    if (!spo2Valid) return;
    setSpo2Log((log) => [...log, { second: Math.round(elapsed), value: Number(spo2Draft) }]);
    setSpo2Draft("");
  }

  /** A `type="number"` input does not enforce max while typing: entering 96 and
   *  then 86 without the first being logged silently produced "9686", which is
   *  out of range and logged nothing. Three digits is the whole domain. */
  function onSpo2Change(next: string) {
    if (next === "" || /^\d{1,3}$/.test(next)) setSpo2Draft(next);
  }

  function finish() {
    setRunning(false);
    // A rest still in progress when the walk ends is real time on the clock.
    let rests = restSeconds;
    if (resting && restStartedAt.current) {
      rests += Math.round((Date.now() - restStartedAt.current) / 1000);
    }
    onFinish({
      seconds: Math.round(elapsed), laps, partial,
      restCount, restSeconds: rests, spo2Log,
    });
  }

  function reset() {
    setRunning(false); setElapsed(0); setLaps(0); setPartial(0);
    setResting(false); setRestCount(0); setRestSeconds(0); setSpo2Log([]);
    accumulated.current = 0; lastPrompt.current = null; restStartedAt.current = null;
    setPrompt(null);
  }

  const remaining = Math.max(TOTAL_SECONDS - elapsed, 0);
  const minutes = Math.floor(remaining / 60);
  const seconds = Math.floor(remaining % 60);
  const done = elapsed >= TOTAL_SECONDS;
  const progress = elapsed / TOTAL_SECONDS;
  const nadir = spo2Log.length ? Math.min(...spo2Log.map((r) => r.value)) : null;

  // Rest time is committed to state when a rest ends, so a rest still running
  // contributed nothing to the total — which is exactly when someone is
  // watching it. `elapsed` re-renders four times a second while the clock
  // runs, so deriving the live figure here is enough to keep it moving.
  const restSecondsShown = resting && restStartedAt.current
    ? restSeconds + Math.round((Date.now() - restStartedAt.current) / 1000)
    : restSeconds;

  return (
    <div className="flex flex-col items-center">
      {/* A ring rather than a bar: it reads as a clock, and the remaining arc is
          legible from across a corridor. */}
      <div className="relative h-[168px] w-[168px]">
        <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90">
          <circle cx="50" cy="50" r="45" fill="none" strokeWidth="6"
            className="stroke-surface-sunk" />
          <circle cx="50" cy="50" r="45" fill="none" strokeWidth="6" strokeLinecap="round"
            className={cn("transition-[stroke-dashoffset] duration-200",
              done ? "stroke-good-fg" : resting ? "stroke-moderate-fg" : "stroke-teal-500")}
            strokeDasharray={2 * Math.PI * 45}
            strokeDashoffset={2 * Math.PI * 45 * (1 - progress)} />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-[34px] font-semibold leading-none tracking-[-0.02em] tnum text-ink">
            {minutes}:{String(seconds).padStart(2, "0")}
          </span>
          <span className={cn(
            "mt-1.5 text-[11px] font-semibold uppercase tracking-[0.07em]",
            resting ? "text-moderate-fg" : "text-ink-faint",
          )}>
            {done ? "Finished" : resting ? "Resting" : running ? "Remaining" : "Ready"}
          </span>
        </div>
      </div>

      <p className="mt-3 min-h-[38px] max-w-[280px] text-center text-[13px] leading-relaxed text-ink-muted">
        {prompt ?? (running ? "Walk at your own pace." : "Press start when the patient begins walking.")}
      </p>

      <div className="mt-1 flex flex-wrap justify-center gap-2">
        {!done && (
          <Button type="button" variant={running ? "secondary" : "primary"}
            onClick={() => setRunning(!running)}>
            {running ? <><Pause size={15} /> Pause</> : <><Play size={15} /> {elapsed > 0 ? "Resume" : "Start"}</>}
          </Button>
        )}
        {running && !done && (
          <Button type="button" variant={resting ? "primary" : "secondary"} onClick={toggleRest}>
            {resting ? "Walking again" : "Patient resting"}
          </Button>
        )}
        <Button type="button" variant="ghost" onClick={reset}>
          <RotateCcw size={15} /> Reset
        </Button>
        {(done || elapsed > 0) && (
          <Button
            type="button"
            // Only the finished state is the primary action. Stopping early is
            // available, not encouraged.
            variant={done ? "primary" : "secondary"}
            onClick={finish}
          >
            <Square size={15} /> {done ? "Record result" : "Stop early"}
          </Button>
        )}
      </div>

      {/* Lap counting: a big target, because whoever is tapping it is also
          watching the patient. */}
      <div className="mt-6 w-full rounded-[12px] border border-line bg-surface-sunk/50 p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-faint">Laps</p>
            <p className="mt-1 text-[26px] font-semibold leading-none tnum text-ink">{laps}</p>
          </div>
          <div className="text-end">
            <p className="text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-faint">Distance</p>
            <p className="mt-1 text-[26px] font-semibold leading-none tnum text-ink">
              {(laps * courseLength + partial).toFixed(0)}
              <span className="ms-1 text-[13px] font-normal text-ink-faint">m</span>
            </p>
          </div>
        </div>
        <div className="mt-3 flex gap-2">
          <Button type="button" variant="secondary" className="h-12 flex-1 text-[15px]"
            onClick={() => setLaps((n) => n + 1)} disabled={!running && !done}>
            + Lap ({courseLength} m)
          </Button>
          <Button type="button" variant="ghost" size="icon" className="h-12"
            onClick={() => setLaps((n) => Math.max(0, n - 1))} aria-label="Remove a lap">
            <Minus size={16} />
          </Button>
        </div>
        <label className="mt-3 block">
          <span className="text-[12px] text-ink-muted">Partial lap at the finish (metres)</span>
          <input
            type="number" min={0} max={courseLength} value={partial || ""}
            onChange={(e) => setPartial(Number(e.target.value) || 0)}
            placeholder="0"
            className="mt-1 h-9 w-full rounded-[9px] border border-line-strong bg-surface px-3 text-sm tnum text-ink focus:border-teal-400 focus:outline-none focus:ring-4 focus:ring-teal-400/12"
          />
        </label>
      </div>

      {/* Oxygen readings, taken as they happen. The nadir is what a clinician
          reads; recording only the value at the finish hides a dip that
          recovered before the six minutes were up. */}
      <div className="mt-3 w-full rounded-[12px] border border-line bg-surface-sunk/50 p-4">
        <div className="flex items-center justify-between gap-3">
          <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.07em] text-ink-faint">
            <Activity size={13} /> SpO₂ during the walk
          </p>
          {nadir !== null && (
            <p className={cn(
              "text-[13px] font-semibold tnum",
              nadir < 88 ? "text-severe-fg" : "text-ink-soft",
            )}>
              lowest {nadir}%
            </p>
          )}
        </div>

        <div className="mt-2.5 flex gap-2">
          <input
            type="number" min={50} max={100} inputMode="numeric"
            value={spo2Draft}
            onChange={(e) => onSpo2Change(e.target.value)}
            // Both, because a numeric keypad sends NumpadEnter, not Enter.
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.code === "NumpadEnter") {
                e.preventDefault();
                logSpo2();
              }
            }}
            placeholder="96"
            aria-label="Oxygen saturation reading"
            className="h-10 w-24 rounded-[9px] border border-line-strong bg-surface px-3 text-sm tnum text-ink focus:border-teal-400 focus:outline-none focus:ring-4 focus:ring-teal-400/12"
          />
          <Button type="button" variant="secondary" className="flex-1" onClick={logSpo2}
            disabled={!spo2Valid}>
            Log reading
          </Button>
        </div>

        {spo2Log.length > 0 && (
          <ul className="mt-2.5 flex flex-wrap gap-1.5">
            {spo2Log.map((r, i) => (
              <li key={i} className={cn(
                "rounded-md px-2 py-1 text-[11.5px] font-medium tnum",
                r.value === nadir ? "bg-severe-bg text-severe-fg" : "bg-surface text-ink-muted",
              )}>
                {Math.floor(r.second / 60)}:{String(r.second % 60).padStart(2, "0")} · {r.value}%
              </li>
            ))}
          </ul>
        )}
      </div>

      {(restCount > 0 || restSecondsShown > 0) && (
        <p className={cn(
          "mt-3 text-[12.5px]",
          resting ? "text-moderate-fg" : "text-ink-muted",
        )}>
          {restCount} rest{restCount === 1 ? "" : "s"} · {restSecondsShown}s stopped in total
        </p>
      )}
    </div>
  );
}
