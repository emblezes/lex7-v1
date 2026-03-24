"use client";

import { useEffect, useState } from "react";
import { useProfile } from "../ProfileContext";
import {
  Radar,
  ChevronRight,
  ExternalLink,
  TrendingUp,
  AlertTriangle,
  Clock,
  Building2,
  BookOpen,
  GraduationCap,
  FileSearch,
} from "lucide-react";

interface AnticipationReport {
  id: number;
  source_type: string;
  source_name: string;
  title: string;
  url: string;
  publication_date: string | null;
  themes: string[];
  resume_ia: string | null;
  policy_recommendations: string[];
  legislative_probability: number | null;
  estimated_timeline: string | null;
  pipeline_stage: string;
  linked_texte_uids: string[];
  is_read: boolean;
}

const SOURCE_ICONS: Record<string, typeof Building2> = {
  think_tank: BookOpen,
  rapport_inspection: FileSearch,
  academic: GraduationCap,
  consultation: Building2,
};

const STAGE_LABELS: Record<string, { label: string; color: string }> = {
  report: { label: "Rapport", color: "bg-blue-100 text-blue-700" },
  recommendation: { label: "Recommandation", color: "bg-amber-100 text-amber-700" },
  proposition: { label: "Proposition", color: "bg-orange-100 text-orange-700" },
  debate: { label: "Débat", color: "bg-red-100 text-red-700" },
  law: { label: "Loi", color: "bg-green-100 text-green-700" },
};

export default function AnticipationPage() {
  const { activeProfile } = useProfile();
  const [reports, setReports] = useState<AnticipationReport[]>([]);
  const [signals, setSignals] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [filter, setFilter] = useState<string>("all");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch("/api/anticipation/reports?limit=50").then((r) => r.json()),
      fetch(
        `/api/anticipation/signals?profile_id=${activeProfile?.id || ""}&days=30`
      ).then((r) => r.json()),
      fetch("/api/anticipation/stats").then((r) => r.json()),
    ])
      .then(([reportsData, signalsData, statsData]) => {
        setReports(reportsData.items || []);
        setSignals(Array.isArray(signalsData) ? signalsData : []);
        setStats(statsData);
      })
      .finally(() => setLoading(false));
  }, [activeProfile]);

  const filtered =
    filter === "all"
      ? reports
      : reports.filter((r) => r.source_type === filter);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-muted">
        Chargement de la veille anticipation...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-serif text-3xl font-bold text-dark">
          Anticipation
        </h1>
        <p className="mt-1 text-sm text-muted">
          Signaux pré-législatifs : rapports, études et recommandations qui
          façonneront les prochaines lois
        </p>
      </div>

      {/* Stats rapides */}
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          <div className="rounded-xl border border-border bg-white p-4">
            <div className="text-2xl font-bold text-dark">{stats.total}</div>
            <div className="text-xs text-muted">Rapports suivis</div>
          </div>
          <div className="rounded-xl border border-border bg-white p-4">
            <div className="text-2xl font-bold text-dark">
              {stats.by_stage?.report || 0}
            </div>
            <div className="text-xs text-muted">Stade rapport</div>
          </div>
          <div className="rounded-xl border border-border bg-white p-4">
            <div className="text-2xl font-bold text-amber-600">
              {stats.by_stage?.recommendation || 0}
            </div>
            <div className="text-xs text-muted">Recommandations actives</div>
          </div>
          <div className="rounded-xl border border-border bg-white p-4">
            <div className="text-2xl font-bold text-red-600">
              {signals.length}
            </div>
            <div className="text-xs text-muted">Signaux pertinents (30j)</div>
          </div>
        </div>
      )}

      {/* Signaux d'anticipation pertinents */}
      {signals.length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
          <h2 className="flex items-center gap-2 font-serif text-lg font-bold text-dark">
            <AlertTriangle className="h-5 w-5 text-amber-600" />
            Signaux d'anticipation pour {activeProfile?.name || "votre entreprise"}
          </h2>
          <div className="mt-3 space-y-3">
            {signals.slice(0, 5).map((signal: any, i: number) => (
              <div
                key={i}
                className="flex items-start gap-3 rounded-lg bg-white p-3"
              >
                <TrendingUp className="mt-0.5 h-4 w-4 flex-shrink-0 text-amber-600" />
                <div className="flex-1">
                  <div className="text-sm font-medium text-dark">
                    {signal.title}
                  </div>
                  <div className="mt-0.5 text-xs text-muted">
                    {signal.source_name} — Pertinence : {signal.relevance}
                    {signal.legislative_probability && (
                      <span className="ml-2 text-amber-700">
                        Probabilité législative :{" "}
                        {Math.round(signal.legislative_probability * 100)}%
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filtres */}
      <div className="flex gap-2">
        {[
          { key: "all", label: "Tous" },
          { key: "think_tank", label: "Think tanks" },
          { key: "rapport_inspection", label: "Inspections" },
          { key: "academic", label: "Académique" },
          { key: "consultation", label: "Consultations" },
        ].map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
              filter === f.key
                ? "bg-dark text-white"
                : "bg-white text-muted hover:bg-cream"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Pipeline visuel */}
      <div className="rounded-xl border border-border bg-white p-5">
        <h2 className="font-serif text-lg font-bold text-dark">
          Pipeline Rapport → Loi
        </h2>
        <div className="mt-4 flex items-center gap-2">
          {Object.entries(STAGE_LABELS).map(([key, { label, color }], i) => (
            <div key={key} className="flex items-center gap-2">
              <div
                className={`rounded-lg px-3 py-1.5 text-xs font-medium ${color}`}
              >
                {label}
                <span className="ml-1 font-bold">
                  {reports.filter((r) => r.pipeline_stage === key).length}
                </span>
              </div>
              {i < 4 && (
                <ChevronRight className="h-4 w-4 text-muted" />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Liste des rapports */}
      <div className="space-y-3">
        {filtered.length === 0 ? (
          <div className="rounded-xl border border-border bg-white p-8 text-center text-muted">
            Aucun rapport d'anticipation pour le moment. Les collecteurs sont en
            cours de configuration.
          </div>
        ) : (
          filtered.map((report) => {
            const Icon =
              SOURCE_ICONS[report.source_type] || BookOpen;
            const stage = STAGE_LABELS[report.pipeline_stage];

            return (
              <div
                key={report.id}
                className="rounded-xl border border-border bg-white p-5 transition-shadow hover:shadow-sm"
              >
                <div className="flex items-start gap-4">
                  <div className="rounded-lg bg-cream p-2">
                    <Icon className="h-5 w-5 text-dark" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-dark">
                        {report.title}
                      </h3>
                      {stage && (
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${stage.color}`}
                        >
                          {stage.label}
                        </span>
                      )}
                    </div>
                    <div className="mt-1 flex items-center gap-3 text-xs text-muted">
                      <span className="font-medium">
                        {report.source_name}
                      </span>
                      {report.publication_date && (
                        <>
                          <span>-</span>
                          <Clock className="h-3 w-3" />
                          <span>
                            {new Date(
                              report.publication_date
                            ).toLocaleDateString("fr-FR")}
                          </span>
                        </>
                      )}
                      {report.legislative_probability != null && (
                        <>
                          <span>-</span>
                          <TrendingUp className="h-3 w-3" />
                          <span>
                            Prob. législative :{" "}
                            {Math.round(
                              report.legislative_probability * 100
                            )}
                            %
                          </span>
                        </>
                      )}
                    </div>
                    {report.resume_ia && (
                      <p className="mt-2 text-sm text-muted line-clamp-2">
                        {report.resume_ia}
                      </p>
                    )}
                    {report.themes.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {report.themes.map((t) => (
                          <span
                            key={t}
                            className="rounded-full bg-cream px-2 py-0.5 text-xs text-muted"
                          >
                            {t}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  {report.url && (
                    <a
                      href={report.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-muted hover:text-dark"
                    >
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
