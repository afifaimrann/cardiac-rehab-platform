import { cn } from "@/lib/utils";

/**
 * Modified Borg CR10 scale, as used for dyspnoea and fatigue in the 6MWT.
 *
 * The anchor words are the scale — a patient rating "4" without seeing
 * "somewhat severe" is guessing, and the descriptors are what make ratings
 * comparable between tests and between people.
 */
const ANCHORS: Record<number, string> = {
  0: "Nothing at all",
  0.5: "Very, very slight",
  1: "Very slight",
  2: "Slight",
  3: "Moderate",
  4: "Somewhat severe",
  5: "Severe",
  7: "Very severe",
  9: "Very, very severe",
  10: "Maximal",
};

const STEPS = [0, 0.5, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

export function BorgScale({ label, value, onChange }: {
  label: string;
  value: number | null;
  onChange: (v: number) => void;
}) {
  return (
    <fieldset>
      <legend className="mb-2 text-[13px] font-medium text-ink-soft">{label}</legend>
      <div className="flex flex-wrap gap-1.5">
        {STEPS.map((step) => (
          <button
            key={step}
            type="button"
            onClick={() => onChange(step)}
            aria-pressed={value === step}
            title={ANCHORS[step] ?? undefined}
            className={cn(
              "h-9 min-w-9 rounded-[9px] border px-2 text-[13px] font-medium tnum transition-colors duration-150",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/40",
              value === step
                ? "border-teal-500 bg-teal-500 text-white"
                : "border-line-strong bg-surface text-ink-soft hover:border-ink-faint hover:text-ink",
            )}
          >
            {step}
          </button>
        ))}
      </div>
      <p className="mt-2 min-h-[18px] text-[12.5px] text-ink-muted">
        {value != null ? ANCHORS[value] ?? "" : "Select a rating"}
      </p>
    </fieldset>
  );
}
