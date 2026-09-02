/**
 * Blood-pressure trend.
 *
 * In its own module and loaded lazily: recharts is by far the heaviest
 * dependency, and only the patient view ever renders a chart. Clinicians never
 * download it.
 */
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export interface BpPoint {
  date: string;
  systolic: number | null;
  diastolic: number | null;
}

export default function BpChart({ data }: { data: BpPoint[] }) {
  return (
    <div className="h-56 px-3 py-4">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
          <CartesianGrid stroke="#eceef2" vertical={false} />
          <XAxis dataKey="date" tick={{ fontSize: 11, fill: "#8a95a8" }}
            tickLine={false} axisLine={{ stroke: "#d9dde5" }} minTickGap={24} />
          <YAxis domain={[50, 200]} tick={{ fontSize: 11, fill: "#8a95a8" }}
            tickLine={false} axisLine={false} width={44} />
          <Tooltip contentStyle={{
            borderRadius: 10, border: "1px solid #d9dde5",
            fontSize: 12, boxShadow: "0 4px 12px rgba(19,27,40,.08)",
          }} />
          <Line type="monotone" dataKey="systolic" stroke="#2f6db5" strokeWidth={2} dot={false} name="Systolic" />
          <Line type="monotone" dataKey="diastolic" stroke="#8a95a8" strokeWidth={2} dot={false} name="Diastolic" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
