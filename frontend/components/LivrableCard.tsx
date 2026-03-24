"use client";

import { useState } from "react";
import {
  FileText,
  Mail,
  FileCheck,
  Scroll,
  Download,
  ChevronDown,
  ChevronUp,
  Pencil,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { type LivrableOut } from "@/lib/api";

const typeConfig: Record<string, { icon: typeof FileText; label: string; color: string }> = {
  note_comex: { icon: FileText, label: "Note COMEX", color: "bg-blue-50 text-blue-700" },
  email: { icon: Mail, label: "Email", color: "bg-emerald-50 text-emerald-700" },
  amendement: { icon: Scroll, label: "Amendement", color: "bg-amber-50 text-amber-700" },
  fiche_position: { icon: FileCheck, label: "Fiche position", color: "bg-purple-50 text-purple-700" },
};

const proseClasses =
  "prose prose-stone prose-sm max-w-none " +
  "[&_h1]:font-serif [&_h1]:text-xl [&_h1]:font-bold [&_h1]:text-stone-900 [&_h1]:mb-3 [&_h1]:mt-4 " +
  "[&_h2]:font-serif [&_h2]:text-lg [&_h2]:font-bold [&_h2]:text-stone-800 [&_h2]:mb-2 [&_h2]:mt-3 " +
  "[&_h3]:font-serif [&_h3]:text-base [&_h3]:font-semibold [&_h3]:text-stone-700 [&_h3]:mb-2 [&_h3]:mt-3 " +
  "[&_p]:text-stone-700 [&_p]:leading-relaxed [&_p]:mb-2 " +
  "[&_strong]:text-stone-900 [&_strong]:font-semibold " +
  "[&_ul]:list-disc [&_ul]:pl-5 [&_ul]:mb-2 " +
  "[&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:mb-2 " +
  "[&_li]:text-stone-700 [&_li]:mb-0.5 " +
  "[&_hr]:border-stone-200 [&_hr]:my-4 " +
  "[&_table]:w-full [&_table]:border-collapse [&_th]:bg-stone-50 [&_th]:border [&_th]:border-stone-200 [&_th]:px-2 [&_th]:py-1.5 [&_th]:text-left [&_th]:text-xs [&_th]:font-semibold " +
  "[&_td]:border [&_td]:border-stone-200 [&_td]:px-2 [&_td]:py-1.5 [&_td]:text-xs";

interface LivrableCardProps {
  livrable: LivrableOut;
  onExportPdf?: () => void;
  onEdit?: () => void;
}

export default function LivrableCard({ livrable, onExportPdf, onEdit }: LivrableCardProps) {
  const [expanded, setExpanded] = useState(false);
  const cfg = typeConfig[livrable.type] || typeConfig.note_comex;
  const Icon = cfg.icon;

  return (
    <div className="rounded-lg border border-border bg-white">
      {/* Header row — using div instead of button to avoid nested buttons */}
      <div
        onClick={() => setExpanded(!expanded)}
        className="flex w-full cursor-pointer items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-muted" />
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${cfg.color}`}>
            {cfg.label}
          </span>
          <span className="text-sm font-medium text-dark">
            {livrable.title}
          </span>
          <span className={`rounded px-1.5 py-0.5 text-xs ${
            livrable.status === "final" ? "bg-emerald-100 text-emerald-700" :
            livrable.status === "sent" ? "bg-blue-100 text-blue-700" :
            "bg-stone-100 text-stone-600"
          }`}>
            {livrable.status}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {onEdit && (
            <button
              onClick={(e) => { e.stopPropagation(); onEdit(); }}
              className="rounded p-1 text-muted hover:bg-cream hover:text-warm"
              title="Ouvrir dans l'editeur"
            >
              <Pencil className="h-4 w-4" />
            </button>
          )}
          {onExportPdf && (
            <button
              onClick={(e) => { e.stopPropagation(); onExportPdf(); }}
              className="rounded p-1 text-muted hover:bg-cream hover:text-dark"
              title="Export PDF"
            >
              <Download className="h-4 w-4" />
            </button>
          )}
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-muted" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted" />
          )}
        </div>
      </div>
      {expanded && livrable.content && (
        <div className="border-t border-border px-6 py-4">
          <div className={proseClasses}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {livrable.content}
            </ReactMarkdown>
          </div>
          <div className="mt-3 flex items-center justify-between border-t border-border/50 pt-3">
            {livrable.created_at && (
              <p className="text-xs text-muted">
                Genere le{" "}
                {new Date(livrable.created_at).toLocaleDateString("fr-FR", {
                  day: "numeric",
                  month: "long",
                  year: "numeric",
                })}
              </p>
            )}
            {onEdit && (
              <button
                onClick={onEdit}
                className="flex items-center gap-1.5 rounded-lg bg-warm/10 px-3 py-1.5 text-xs font-medium text-warm transition hover:bg-warm/20"
              >
                <Pencil className="h-3 w-3" />
                Modifier dans l&apos;editeur
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
