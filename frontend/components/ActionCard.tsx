import Link from "next/link";
import { FileText, Mail, PenTool, Eye } from "lucide-react";

const typeIcons: Record<string, typeof FileText> = {
  draft_note: FileText,
  draft_email: Mail,
  draft_amendment: PenTool,
  monitor: Eye,
};

const typeLabels: Record<string, string> = {
  draft_note: "Note",
  draft_email: "Email",
  draft_amendment: "Amendement",
  monitor: "Surveillance",
};

interface ActionCardProps {
  priority?: number;
  label: string;
  type?: string;
  deadline?: string;
  who?: string;
  href?: string;
  rationale?: string;
}

export default function ActionCard({
  priority,
  label,
  type,
  deadline,
  who,
  href,
  rationale,
}: ActionCardProps) {
  const Icon = (type && typeIcons[type]) || FileText;

  const card = (
    <div className="group flex gap-4 rounded-xl border border-border bg-white p-5 transition-all hover:shadow-md">
      {priority !== undefined && (
        <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-warm text-sm font-bold text-white">
          {priority}
        </div>
      )}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 flex-shrink-0 text-muted" />
          <p className="text-sm font-medium text-dark group-hover:text-warm">
            {label}
          </p>
        </div>
        {rationale && (
          <p className="mt-1 text-xs text-muted line-clamp-2">{rationale}</p>
        )}
        <div className="mt-2 flex flex-wrap gap-2 text-xs">
          {deadline && (
            <span className="rounded bg-stone-100 px-2 py-0.5 font-medium text-stone-600">
              {deadline}
            </span>
          )}
          {who && (
            <span className="rounded bg-warm/10 px-2 py-0.5 font-medium text-warm">
              {who}
            </span>
          )}
        </div>
      </div>
    </div>
  );

  if (href) {
    return <Link href={href}>{card}</Link>;
  }
  return card;
}
