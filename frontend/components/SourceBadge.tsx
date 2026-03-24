import { Landmark } from "lucide-react";

const sourceConfig: Record<string, { label: string; color: string }> = {
  assemblee: { label: "Assemblee nationale", color: "bg-blue-100 text-blue-800" },
  senat: { label: "Senat", color: "bg-purple-100 text-purple-800" },
  jorf: { label: "Journal officiel", color: "bg-rose-100 text-rose-800" },
  gouvernement: { label: "Gouvernement", color: "bg-slate-100 text-slate-700" },
  regulateur: { label: "Regulateur", color: "bg-teal-100 text-teal-800" },
  presse: { label: "Presse", color: "bg-sky-100 text-sky-800" },
  eurlex: { label: "EUR-Lex", color: "bg-indigo-100 text-indigo-800" },
};

export default function SourceBadge({ source }: { source?: string }) {
  if (!source) return null;
  const cfg = sourceConfig[source] || { label: source, color: "bg-stone-100 text-stone-600" };
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${cfg.color}`}>
      <Landmark className="h-3 w-3" />
      {cfg.label}
    </span>
  );
}
