import { levelColors, levelLabels } from "./utils";

export default function SeverityBadge({ level }: { level: string }) {
  return (
    <span
      className={`rounded-full px-2.5 py-0.5 text-xs font-bold uppercase ${
        levelColors[level] || levelColors.medium
      }`}
    >
      {levelLabels[level] || level}
    </span>
  );
}
