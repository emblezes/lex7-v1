import Link from "next/link";
import { timeAgo } from "./utils";

export type TimelineEventType = "alert" | "texte" | "reunion" | "signal" | "change";

const dotColors: Record<TimelineEventType, string> = {
  alert: "bg-red-500",       // rouge pour menaces, vert pour opp via override
  texte: "bg-blue-500",
  reunion: "bg-purple-500",
  signal: "bg-amber-500",
  change: "bg-stone-400",
};

export interface TimelineItem {
  id: string;
  type: TimelineEventType;
  date: string | null;
  summary: string;
  tags?: string[];
  href?: string;
  dotColor?: string; // override pour menace/opp
}

export default function TimelineEvent({ item }: { item: TimelineItem }) {
  const dot = item.dotColor || dotColors[item.type] || "bg-stone-400";

  const content = (
    <div className="group flex gap-3 rounded-lg px-3 py-2.5 transition-colors hover:bg-cream">
      <div className="mt-1.5 flex flex-col items-center">
        <div className={`h-2.5 w-2.5 rounded-full ${dot}`} />
        <div className="mt-1 h-full w-px bg-border" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-dark leading-relaxed">{item.summary}</p>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          {item.date && (
            <span className="text-xs text-muted">{timeAgo(item.date)}</span>
          )}
          {item.tags?.map((tag) => (
            <span
              key={tag}
              className="rounded bg-cream px-1.5 py-0.5 text-xs text-muted"
            >
              {tag}
            </span>
          ))}
        </div>
      </div>
    </div>
  );

  if (item.href) {
    return <Link href={item.href}>{content}</Link>;
  }
  return content;
}
