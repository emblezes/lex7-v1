"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { FolderOpen, Filter } from "lucide-react";
import { useProfile } from "../ProfileContext";
import { fetchTextesSuivis, type TexteBrief } from "@/lib/api";
import SourceBadge from "@/components/SourceBadge";
import SeverityBadge from "@/components/SeverityBadge";
import EmptyState from "@/components/EmptyState";
import { formatEur, timeAgo, levelBorder } from "@/components/utils";

const phaseLabels: Record<string, string> = {
  watching: "En commission",
  escalated: "Vote imminent",
  resolved: "Promulgue",
};

const impactOrder: Record<string, number> = {
  critical: 4,
  high: 3,
  medium: 2,
  low: 1,
};

type FilterLevel = "all" | "critical" | "high" | "medium" | "low";
type FilterThreat = "all" | "threat" | "opportunity";

export default function DossiersPage() {
  const { activeProfile } = useProfile();
  const [briefs, setBriefs] = useState<TexteBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterLevel, setFilterLevel] = useState<FilterLevel>("all");
  const [filterThreat, setFilterThreat] = useState<FilterThreat>("all");

  useEffect(() => {
    if (!activeProfile) return;
    setLoading(true);
    fetchTextesSuivis(activeProfile.id)
      .then(setBriefs)
      .catch(() => setBriefs([]))
      .finally(() => setLoading(false));
  }, [activeProfile]);

  const filtered = useMemo(() => {
    let list = [...briefs];
    if (filterLevel !== "all") {
      list = list.filter((b) => b.impact_level === filterLevel);
    }
    if (filterThreat === "threat") {
      list = list.filter((b) => b.is_threat);
    } else if (filterThreat === "opportunity") {
      list = list.filter((b) => !b.is_threat);
    }
    // Sort: impact desc, then updated_at desc
    list.sort((a, b) => {
      const ia = impactOrder[a.impact_level] || 0;
      const ib = impactOrder[b.impact_level] || 0;
      if (ib !== ia) return ib - ia;
      const da = a.updated_at ? new Date(a.updated_at).getTime() : 0;
      const db = b.updated_at ? new Date(b.updated_at).getTime() : 0;
      return db - da;
    });
    return list;
  }, [briefs, filterLevel, filterThreat]);

  if (!activeProfile) {
    return (
      <div className="flex h-96 items-center justify-center text-muted">
        Selectionnez un client pour voir les dossiers.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-warm border-t-transparent" />
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-serif text-2xl font-bold text-dark">
            Textes & Dossiers
          </h1>
          <p className="mt-1 text-sm text-muted">
            {activeProfile.name} — {briefs.length} dossier{briefs.length !== 1 ? "s" : ""} sous surveillance
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <Filter className="h-4 w-4 text-muted" />
        {(["all", "critical", "high", "medium", "low"] as FilterLevel[]).map((level) => (
          <button
            key={level}
            onClick={() => setFilterLevel(level)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              filterLevel === level
                ? "bg-dark text-white"
                : "bg-white text-muted hover:bg-cream"
            }`}
          >
            {level === "all" ? "Tous" : level === "critical" ? "Critique" : level === "high" ? "Eleve" : level === "medium" ? "Moyen" : "Faible"}
          </button>
        ))}
        <span className="mx-2 text-border">|</span>
        {(["all", "threat", "opportunity"] as FilterThreat[]).map((t) => (
          <button
            key={t}
            onClick={() => setFilterThreat(t)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              filterThreat === t
                ? "bg-dark text-white"
                : "bg-white text-muted hover:bg-cream"
            }`}
          >
            {t === "all" ? "Tous" : t === "threat" ? "Menaces" : "Opportunites"}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          icon={FolderOpen}
          title="Aucun dossier"
          description={
            briefs.length === 0
              ? `Les textes sont automatiquement suivis quand ils concernent les secteurs de ${activeProfile.name}.`
              : "Aucun dossier ne correspond aux filtres selectionnes."
          }
        />
      ) : (
        <div className="space-y-3">
          {filtered.map((b) => {
            const phase = b.followup?.status ? phaseLabels[b.followup.status] || b.followup.status : null;
            const nextDate = b.followup?.next_check_at;

            return (
              <Link
                key={b.id}
                href={`/dashboard/dossiers/${b.texte_uid}`}
                className={`group block rounded-xl border-l-4 ${
                  levelBorder[b.impact_level] || levelBorder.medium
                } border border-border bg-white p-5 transition-all hover:shadow-md`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <SourceBadge source={b.texte?.source} />
                      <SeverityBadge level={b.impact_level} />
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                          b.is_threat
                            ? "bg-red-50 text-red-700"
                            : "bg-emerald-50 text-emerald-700"
                        }`}
                      >
                        {b.is_threat ? "Menace" : "Opportunite"}
                      </span>
                      {phase && (
                        <span className="rounded bg-purple-50 px-2 py-0.5 text-xs font-medium text-purple-700">
                          {phase}
                        </span>
                      )}
                    </div>

                    <h3 className="mt-2 font-serif text-lg font-semibold text-dark group-hover:text-warm">
                      {b.texte?.titre || b.texte_uid}
                    </h3>

                    <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-muted">
                      <span>{b.nb_amendements_analyzed} amendements</span>
                      <span>{b.nb_groupes} groupes</span>
                      {nextDate && (
                        <span className="text-purple-600">
                          Prochaine echeance : {new Date(nextDate).toLocaleDateString("fr-FR")}
                        </span>
                      )}
                      <span className="ml-auto">{timeAgo(b.updated_at)}</span>
                    </div>
                  </div>

                  {b.exposure_eur ? (
                    <div className="flex-shrink-0 text-right">
                      <div className="text-xl font-bold text-dark">
                        {formatEur(b.exposure_eur)}
                      </div>
                      <div className="text-xs text-muted">exposition</div>
                    </div>
                  ) : null}
                </div>
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}
