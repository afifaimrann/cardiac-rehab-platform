/**
 * Blood-pressure trend.
 *
 * Lazily loaded in its own chunk: recharts is the heaviest dependency and only
 * the patient overview renders a chart, so clinicians never download it.
 */
import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export interface BpPoint {
  date: string;
  systolic: number | null;
  diastolic: number | null;
}

/** Read palette values from CSS so the chart follows the active theme. */
function usePalette() {
  const [palette, setPalette] = useState({
    line: "#e7e2d9", muted: "#7d766c", accent: "#a8562f", surface: "#ffffff", ink: "#1c1a17",
  });

  useEffect(() => {
    const read = () => {
      const s = getComputedStyle(document.documentElement);
      const get = (name: string, fallback: string) =>
        s.getPropertyValue(name).trim() || fallback;
      setPalette({
        line: get("--color-line", "#e7e2d9"),
        muted: get("--color-ink-muted", "#7d766c"),
        accent: get("--color-accent-500", "#a8562f"),
        surface: get("--color-surface", "#ffffff"),
        ink: get("--color-ink", "#1c1a17"),
      });
    };
    read();
    const observer = new MutationObserver(read);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  return palette;
}

export default function BpChart({ data }: { data: BpPoint[] }) {
  const palette = usePalette();

  return (
    <div className="h-[286px] px-3 py-5">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 10, bottom: 0, left: -18 }}>
          <CartesianGrid stroke={palette.line} vertical={false} />
          <XAxis dataKey="date" tick={{ fontSize: 11, fill: palette.muted }}
            tickLine={false} axisLine={{ stroke: palette.line }} minTickGap={26} />
          <YAxis domain={[50, 200]} tick={{ fontSize: 11, fill: palette.muted }}
            tickLine={false} axisLine={false} width={44} />
          <Tooltip
            contentStyle={{
              borderRadius: 12, border: `1px solid ${palette.line}`,
              background: palette.surface, color: palette.ink,
              fontSize: 12, boxShadow: "0 8px 24px -12px rgba(28,26,23,.25)",
            }}
            cursor={{ stroke: palette.line }}
          />
          <Line type="monotone" dataKey="systolic" stroke={palette.accent} strokeWidth={2}
            dot={false} name="Systolic" />
          <Line type="monotone" dataKey="diastolic" stroke={palette.muted} strokeWidth={1.75}
            dot={false} strokeDasharray="4 3" name="Diastolic" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
