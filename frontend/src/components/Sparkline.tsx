/**
 * A trend at a glance, with the healthy range drawn behind it.
 *
 * A bare line says "it went up"; a line against its normal band says "it went
 * up and it is still fine", which is the question a patient is actually asking.
 */
export function Sparkline({
  values, min, max, band, tone = "normal", width = 108, height = 32,
}: {
  values: (number | null)[];
  min: number;
  max: number;
  band?: [number, number];
  tone?: "normal" | "warn" | "bad";
  width?: number;
  height?: number;
}) {
  const points = values.filter((v): v is number => v != null);
  if (points.length < 2) {
    return <div className="h-8 w-[108px] rounded bg-surface-sunk/60" aria-hidden />;
  }

  const scaleY = (v: number) => height - ((v - min) / (max - min)) * height;
  const scaleX = (i: number) => (i / (points.length - 1)) * width;
  const path = points.map((v, i) => `${i === 0 ? "M" : "L"}${scaleX(i).toFixed(1)},${scaleY(v).toFixed(1)}`).join(" ");
  const stroke = tone === "bad" ? "var(--color-severe-fg)"
    : tone === "warn" ? "var(--color-moderate-fg)"
    : "var(--color-teal-500)";

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}
      className="overflow-visible" role="img" aria-label="Recent trend">
      {band && (
        <rect
          x={0} y={scaleY(band[1])} width={width}
          height={Math.max(scaleY(band[0]) - scaleY(band[1]), 1)}
          fill="var(--color-good-fg)" opacity={0.09} rx={2}
        />
      )}
      <path d={path} fill="none" stroke={stroke} strokeWidth={1.75}
        strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={scaleX(points.length - 1)} cy={scaleY(points[points.length - 1])}
        r={2.5} fill={stroke} />
    </svg>
  );
}
