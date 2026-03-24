"use client";

interface InfluenceGaugeProps {
  score: number; // 0-100
  size?: "sm" | "md";
}

export default function InfluenceGauge({ score, size = "md" }: InfluenceGaugeProps) {
  const pct = Math.round(Math.min(Math.max(score, 0), 100));
  const color =
    pct >= 70 ? "bg-red-500" : pct >= 40 ? "bg-amber-400" : "bg-emerald-400";
  const textColor =
    pct >= 70 ? "text-red-700" : pct >= 40 ? "text-amber-700" : "text-emerald-700";

  if (size === "sm") {
    return (
      <div className="flex items-center gap-1.5">
        <div className="h-1.5 w-12 rounded-full bg-stone-200">
          <div
            className={`h-1.5 rounded-full transition-all ${color}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className={`text-xs font-bold ${textColor}`}>{pct}</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <div className="h-2.5 w-20 rounded-full bg-stone-200">
        <div
          className={`h-2.5 rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`text-sm font-bold ${textColor}`}>{pct}</span>
    </div>
  );
}
