type RingTone = "gold" | "teal" | "coral";
type RingSize = "sm" | "md";

const toneMap: Record<RingTone, { stroke: string; text: string; track: string }> = {
  gold: { stroke: "var(--gold)", text: "var(--gold-text)", track: "var(--border-hi)" },
  teal: { stroke: "var(--teal)", text: "var(--teal-text)", track: "var(--border-hi)" },
  coral: { stroke: "var(--coral)", text: "var(--coral-text)", track: "var(--border-hi)" },
};

const sizeMap: Record<RingSize, { box: number; radius: number; strokeWidth: number; fontSize: number }> = {
  sm: { box: 26, radius: 10, strokeWidth: 2.2, fontSize: 9.5 },
  md: { box: 38, radius: 16, strokeWidth: 3, fontSize: 11 },
};

type TrustRingProps = {
  value: number;
  max?: number;
  tone?: RingTone;
  colorRole?: RingTone;
  size?: RingSize;
  suffix?: string;
  className?: string;
};

export function TrustRing({
  value,
  max = 10,
  tone,
  colorRole,
  size = "md",
  suffix = "",
  className = "",
}: TrustRingProps) {
  const resolvedTone = colorRole ?? tone ?? "gold";
  const palette = toneMap[resolvedTone];
  const metrics = sizeMap[size];
  const clampedValue = Math.max(0, Math.min(value, max));
  const progress = clampedValue / max;
  const circumference = 2 * Math.PI * metrics.radius;
  const strokeDashoffset = circumference * (1 - progress);

  return (
    <div
      className={className}
      style={{
        width: metrics.box,
        height: metrics.box,
        position: "relative",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <svg width={metrics.box} height={metrics.box} viewBox={`0 0 ${metrics.box} ${metrics.box}`} aria-hidden="true">
        <circle
          cx={metrics.box / 2}
          cy={metrics.box / 2}
          r={metrics.radius}
          fill="none"
          stroke={palette.track}
          strokeWidth={metrics.strokeWidth}
        />
        <circle
          cx={metrics.box / 2}
          cy={metrics.box / 2}
          r={metrics.radius}
          fill="none"
          stroke={palette.stroke}
          strokeWidth={metrics.strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          transform={`rotate(-90 ${metrics.box / 2} ${metrics.box / 2})`}
        />
      </svg>
      <span
        className="font-mono font-medium"
        style={{
          position: "absolute",
          color: palette.text,
          fontSize: metrics.fontSize,
          lineHeight: 1,
        }}
      >
        {value.toFixed(size === "sm" ? 0 : 1)}
        {suffix}
      </span>
    </div>
  );
}
