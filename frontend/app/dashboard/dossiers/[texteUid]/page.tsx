"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Shield,
  Users,
  Target,
  Phone,
  ClipboardList,
  RefreshCw,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Clock,
  Zap,
  FileText,
  Mic,
  Newspaper,
  Calendar,
  Loader2,
} from "lucide-react";
import { useProfile } from "../../ProfileContext";
import {
  fetchTexteBrief,
  refreshTexteBrief,
  fetchDossierActions,
  fetchDossierEvenements,
  fetchDossierActeursCles,
  generateDossierActions,
  generateLivrable,
  type TexteBrief,
  type ForceMapEntry,
  type CriticalAmendment,
  type KeyContact,
  type ActionPlanItem,
  type ActionTask,
  type EvenementOut,
  type ActeurInfluence,
  type LivrableOut,
} from "@/lib/api";
import SourceBadge from "@/components/SourceBadge";
import SeverityBadge from "@/components/SeverityBadge";
import InfluenceGauge from "@/components/InfluenceGauge";
import LivrableCard from "@/components/LivrableCard";
import DossierChat from "@/components/DossierChat";
import dynamic from "next/dynamic";
const DocumentWorkspace = dynamic(
  () => import("@/components/DocumentWorkspace"),
  { ssr: false },
);
import { formatEur } from "@/components/utils";

/* ── Config ── */

const positionConfig: Record<
  string,
  { border: string; bg: string; badge: string; label: string; barColor: string }
> = {
  contre: {
    border: "border-red-300",
    bg: "bg-red-50",
    badge: "bg-red-200 text-red-800",
    label: "Opposition",
    barColor: "bg-red-500",
  },
  pour: {
    border: "border-emerald-300",
    bg: "bg-emerald-50",
    badge: "bg-emerald-200 text-emerald-800",
    label: "Soutien",
    barColor: "bg-emerald-500",
  },
  mixte: {
    border: "border-amber-300",
    bg: "bg-amber-50",
    badge: "bg-amber-200 text-amber-800",
    label: "Position mixte",
    barColor: "bg-amber-400",
  },
};

const eventIcons: Record<string, typeof FileText> = {
  amendement: FileText,
  vote: Target,
  declaration: Mic,
  presse: Newspaper,
  commission: Calendar,
  signal: Zap,
  alerte: AlertTriangle,
  suivi: Clock,
};

const severityColors: Record<string, string> = {
  critical: "bg-red-500",
  warning: "bg-amber-400",
  info: "bg-stone-400",
};

/* ── Helpers ── */

function formatSummary(raw: string | null): string[] {
  if (!raw) return [];
  const cleaned = raw.replace(/\*\*/g, "");
  const sentences = cleaned
    .split(/(?<=[.!?])\s+(?=[A-Z\u00C0-\u00DC])/)
    .map((s) => s.trim())
    .filter((s) => s.length > 10);
  return sentences.length > 0 ? sentences : [cleaned];
}

function formatAnalyse(raw: string): string[] {
  if (!raw) return [];
  const parts = raw
    .split(/[.!]\s+/)
    .map((s) => s.trim().replace(/\.$/, ""))
    .filter((s) => s.length > 10);
  return parts.length > 0 ? parts : [raw];
}

function RichText({ text }: { text: string }) {
  const parts = text.split(
    /(\d+[.,]?\d*\s*(?:%|M\u20ac|Md\u20ac|EUR|K\u20ac|cosignataires|amendements?|d\u00e9put\u00e9s?))/gi,
  );
  return (
    <span>
      {parts.map((part, i) =>
        /\d/.test(part) ? (
          <strong key={i} className="font-semibold text-dark">
            {part}
          </strong>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </span>
  );
}

/* ── Sub-components ── */

function ScoreBar({ score, uid }: { score: number; uid?: string }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 20 ? "bg-red-500" : pct >= 10 ? "bg-amber-400" : "bg-emerald-400";
  const inner = (
    <div className="flex items-center gap-2">
      <div className="h-2.5 w-24 rounded-full bg-stone-200">
        <div
          className={`h-2.5 rounded-full transition-all ${color}`}
          style={{ width: `${Math.min(pct * 3, 100)}%` }}
        />
      </div>
      <span className="text-sm font-bold text-dark">{pct}%</span>
    </div>
  );
  if (uid) {
    return (
      <Link href={`/dashboard/acteurs/${uid}`} className="hover:opacity-80">
        {inner}
      </Link>
    );
  }
  return inner;
}

function ForceMapChart({ groups }: { groups: ForceMapEntry[] }) {
  const maxAmdts = Math.max(...groups.map((g) => g.nb_amendements), 1);
  return (
    <div className="mb-6 rounded-xl border border-border bg-white p-6">
      <div className="space-y-3">
        {groups.map((g) => {
          const cfg = positionConfig[g.position] || positionConfig.mixte;
          const pct = Math.round((g.nb_amendements / maxAmdts) * 100);
          return (
            <div key={g.groupe} className="flex items-center gap-3">
              <div className="w-20 text-right">
                <span className="text-sm font-bold text-dark">{g.groupe}</span>
              </div>
              <div className="flex-1">
                <div className="relative h-8 rounded-lg bg-stone-100">
                  <div
                    className={`absolute inset-y-0 left-0 rounded-lg ${cfg.barColor} transition-all`}
                    style={{ width: `${pct}%` }}
                  />
                  <div className="absolute inset-0 flex items-center px-3">
                    <span className="text-xs font-bold text-white drop-shadow-sm">
                      {g.nb_amendements} amdt{g.nb_amendements > 1 ? "s" : ""}
                    </span>
                  </div>
                </div>
              </div>
              <div className="w-24 text-right">
                <span
                  className={`inline-block rounded-full px-2 py-0.5 text-xs font-semibold ${cfg.badge}`}
                >
                  {cfg.label}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Main Page ── */

export default function DossierDetailPage() {
  const params = useParams();
  const texteUid = params.texteUid as string;
  const { activeProfile, loading: profileLoading } = useProfile();
  const [brief, setBrief] = useState<TexteBrief | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  // New enriched data
  const [actions, setActions] = useState<ActionTask[]>([]);
  const [evenements, setEvenements] = useState<EvenementOut[]>([]);
  const [acteursCles, setActeursCles] = useState<ActeurInfluence[]>([]);
  const [generatingActions, setGeneratingActions] = useState(false);
  const [generatingLivrable, setGeneratingLivrable] = useState<number | null>(null);
  const [workspace, setWorkspace] = useState<{
    action: ActionTask;
    type: string;
    existingLivrable?: LivrableOut;
  } | null>(null);

  useEffect(() => {
    if (profileLoading) return;
    if (!activeProfile || !texteUid) {
      setLoading(false);
      return;
    }
    setLoading(true);
    Promise.all([
      fetchTexteBrief(activeProfile.id, texteUid).catch(() => null),
      fetchDossierActions(texteUid).catch(() => []),
      fetchDossierEvenements(texteUid).catch(() => []),
      fetchDossierActeursCles(texteUid).catch(() => []),
    ])
      .then(async ([b, a, e, ac]) => {
        setBrief(b);
        setActions(a as ActionTask[]);
        setEvenements(e as EvenementOut[]);
        setActeursCles(ac as ActeurInfluence[]);

        // Auto-generate actions if none exist and brief is loaded
        if (b && (a as ActionTask[]).length === 0) {
          setGeneratingActions(true);
          try {
            const newActions = await generateDossierActions(texteUid);
            setActions(newActions);
          } catch {
            /* ignore — user can retry manually */
          }
          setGeneratingActions(false);
        }
      })
      .finally(() => setLoading(false));
  }, [activeProfile, texteUid, profileLoading]);

  const handleRefresh = async () => {
    if (!activeProfile) return;
    setRefreshing(true);
    try {
      const updated = await refreshTexteBrief(activeProfile.id, texteUid);
      setBrief(updated);
    } catch {
      /* ignore */
    }
    setRefreshing(false);
  };

  const handleGenerateActions = async () => {
    setGeneratingActions(true);
    try {
      const newActions = await generateDossierActions(texteUid);
      setActions((prev) => [...newActions, ...prev]);
    } catch {
      /* ignore */
    }
    setGeneratingActions(false);
  };

  const handleGenerateLivrable = async (actionId: number, type: string) => {
    setGeneratingLivrable(actionId);
    try {
      const livrable = await generateLivrable(actionId, type);
      // Update the action's livrables list
      setActions((prev) =>
        prev.map((a) =>
          a.id === actionId
            ? { ...a, livrables: [...(a.livrables || []), livrable] }
            : a,
        ),
      );
    } catch {
      /* ignore */
    }
    setGeneratingLivrable(null);
  };

  const toggleGroup = (g: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(g)) next.delete(g);
      else next.add(g);
      return next;
    });
  };

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-warm border-t-transparent" />
      </div>
    );
  }

  if (!brief) {
    return (
      <div className="flex h-96 flex-col items-center justify-center gap-4">
        <p className="text-muted">Brief non trouve pour ce texte.</p>
        <Link
          href="/dashboard/dossiers"
          className="text-sm text-warm hover:underline"
        >
          Retour aux dossiers
        </Link>
      </div>
    );
  }

  const summaryBullets = formatSummary(brief.executive_summary);

  // Group critical amendments by article_vise
  const amendmentsByArticle: Record<string, CriticalAmendment[]> = {};
  for (const a of brief.critical_amendments || []) {
    const article = a.numero?.match(/Art\.?\s*\d+/)?.[0] || "Autres articles";
    if (!amendmentsByArticle[article]) amendmentsByArticle[article] = [];
    amendmentsByArticle[article].push(a);
  }

  const priorityLabel = (p: number | null) => {
    if (!p) return "P3";
    if (p === 1) return "P1 — Urgent";
    if (p === 2) return "P2 — Important";
    return `P${p}`;
  };

  const priorityColor = (p: number | null) => {
    if (p === 1) return "bg-red-100 text-red-700";
    if (p === 2) return "bg-amber-100 text-amber-700";
    return "bg-stone-100 text-stone-600";
  };

  return (
    <div className="mx-auto max-w-5xl">
      {/* Back + refresh */}
      <div className="mb-6 flex items-center justify-between">
        <Link
          href="/dashboard/dossiers"
          className="flex items-center gap-2 text-sm text-muted hover:text-dark"
        >
          <ArrowLeft className="h-4 w-4" />
          Dossiers
        </Link>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="flex items-center gap-2 rounded-lg border border-border bg-white px-4 py-2 text-sm font-medium text-muted transition hover:border-warm hover:text-dark disabled:opacity-50"
        >
          <RefreshCw
            className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`}
          />
          Actualiser l&apos;analyse
        </button>
      </div>

      {/* ────── 1. HEADER ────── */}
      <div className="mb-8 rounded-xl border border-border bg-white p-6">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityBadge level={brief.impact_level} />
          <span
            className={`rounded-full px-3 py-1 text-xs font-semibold ${
              brief.is_threat
                ? "bg-red-50 text-red-700"
                : "bg-emerald-50 text-emerald-700"
            }`}
          >
            {brief.is_threat ? "Menace" : "Opportunite"}
          </span>
          {brief.texte?.type_code && (
            <span className="rounded bg-stone-100 px-2 py-0.5 text-xs font-medium text-stone-600">
              {brief.texte.type_code}
            </span>
          )}
          <SourceBadge source={brief.texte?.source} />
          <span className="text-xs text-muted">v{brief.version}</span>
        </div>

        <h1 className="mt-3 font-serif text-2xl font-bold text-dark">
          {brief.texte?.titre || brief.texte_uid}
        </h1>

        {/* Stats row */}
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div className="rounded-lg bg-cream p-3 text-center">
            <div className="text-2xl font-bold text-dark">
              {brief.nb_amendements_analyzed}
            </div>
            <div className="text-xs text-muted">Amendements</div>
          </div>
          <div className="rounded-lg bg-cream p-3 text-center">
            <div className="text-2xl font-bold text-dark">
              {brief.nb_groupes}
            </div>
            <div className="text-xs text-muted">Groupes</div>
          </div>
          <div className="rounded-lg bg-cream p-3 text-center">
            <div className="text-2xl font-bold text-dark">
              {brief.nb_deputes}
            </div>
            <div className="text-xs text-muted">Deputes</div>
          </div>
          <div className="rounded-lg bg-cream p-3 text-center">
            <div className="text-2xl font-bold text-dark">
              {formatEur(brief.exposure_eur)}
            </div>
            <div className="text-xs text-muted">Exposition</div>
          </div>
        </div>

        {/* Executive summary */}
        <div className="mt-5 rounded-lg border border-amber-200 bg-amber-50/60 p-5">
          <h3 className="mb-3 text-xs font-bold uppercase tracking-wider text-amber-700">
            Resume executif
          </h3>
          <ul className="space-y-2.5">
            {summaryBullets.map((bullet, i) => (
              <li key={i} className="flex gap-3 text-sm leading-relaxed text-dark">
                <span className="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full bg-amber-400" />
                <RichText text={bullet} />
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* ────── 2. CLAUSES A RISQUE ────── */}
      {Object.keys(amendmentsByArticle).length > 0 && (
        <section className="mb-8">
          <h2 className="mb-4 flex items-center gap-2 font-serif text-xl font-bold text-dark">
            <AlertTriangle className="h-5 w-5 text-red-500" />
            Clauses a risque pour vous
          </h2>
          <div className="space-y-4">
            {Object.entries(amendmentsByArticle).map(([article, amendments]) => (
              <div
                key={article}
                className="rounded-xl border border-red-200 bg-red-50/30 p-5"
              >
                <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-red-700">
                  {article}
                </h3>
                <ul className="space-y-3">
                  {amendments.map((a, i) => (
                    <li key={a.uid || i} className="rounded-lg bg-white p-4">
                      <div className="flex items-center gap-2 mb-2">
                        <span className="rounded bg-stone-800 px-2 py-0.5 text-xs font-bold text-white">
                          {a.numero?.startsWith("AS") ? a.numero : `AS${a.numero}`}
                        </span>
                        <Link
                          href={`/dashboard/acteurs/${a.uid || ""}`}
                          className="text-sm font-semibold text-dark hover:text-warm"
                        >
                          {a.auteur}
                          <ExternalLink className="ml-1 inline h-3 w-3 opacity-40" />
                        </Link>
                        <span className="rounded bg-stone-100 px-2 py-0.5 text-xs text-stone-600">
                          {a.groupe}
                        </span>
                        <ScoreBar score={a.adoption_score} />
                      </div>
                      {a.resume && (
                        <p className="text-sm text-dark mb-1">
                          <RichText text={a.resume} />
                        </p>
                      )}
                      {a.why_critical && (
                        <p className="text-sm text-amber-800 bg-amber-50/50 rounded px-3 py-2">
                          <RichText text={a.why_critical} />
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ────── 3. ACTIONS RECOMMANDEES — WORKSPACE AGENT ────── */}
      <section className="mb-8">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="flex items-center gap-2 font-serif text-xl font-bold text-dark">
            <Zap className="h-5 w-5 text-warm" />
            Actions recommandees IA
          </h2>
          <button
            onClick={handleGenerateActions}
            disabled={generatingActions}
            className="flex items-center gap-2 rounded-lg bg-dark px-4 py-2 text-sm font-medium text-white transition hover:bg-dark/80 disabled:opacity-50"
          >
            {generatingActions ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Zap className="h-4 w-4" />
            )}
            {generatingActions ? "Generation..." : "Generer les actions IA"}
          </button>
        </div>

        {actions.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border bg-cream/50 p-8 text-center">
            <Zap className="mx-auto h-8 w-8 text-warm/30" />
            <p className="mt-2 text-sm text-muted">
              Aucune action generee. Cliquez sur &quot;Generer les actions IA&quot; pour commencer.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {actions.map((action) => (
              <div
                key={action.id}
                className="rounded-xl border border-border bg-white p-5 transition-shadow hover:shadow-sm"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${priorityColor(action.priority)}`}>
                        {priorityLabel(action.priority)}
                      </span>
                      <span className="rounded bg-stone-100 px-2 py-0.5 text-xs font-medium text-stone-600">
                        {action.action_type}
                      </span>
                      <span className={`rounded px-1.5 py-0.5 text-xs ${
                        action.status === "completed" ? "bg-emerald-100 text-emerald-700" :
                        action.status === "in_progress" ? "bg-blue-100 text-blue-700" :
                        "bg-stone-100 text-stone-500"
                      }`}>
                        {action.status}
                      </span>
                    </div>
                    <p className="mt-2 text-sm font-medium text-dark">
                      {action.label}
                    </p>
                    {action.rationale && (
                      <p className="mt-1 text-xs text-muted">
                        {action.rationale}
                      </p>
                    )}
                  </div>

                  {/* Boutons pour ouvrir le workspace de redaction */}
                  <div className="flex gap-1.5">
                    {[
                      { type: "note_comex", label: "Rediger Note", icon: "FileText" },
                      { type: "email", label: "Rediger Email", icon: "Mail" },
                      { type: "fiche_position", label: "Rediger Fiche", icon: "FileCheck" },
                    ].map(({ type, label }) => (
                      <button
                        key={type}
                        onClick={() => {
                          // Chercher un livrable existant de ce type
                          const existing = action.livrables?.find((l) => l.type === type);
                          setWorkspace({
                            action,
                            type,
                            existingLivrable: existing,
                          });
                        }}
                        className="rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted transition hover:border-warm hover:bg-warm/5 hover:text-warm"
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Livrables existants */}
                {action.livrables && action.livrables.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {action.livrables.map((l) => (
                      <LivrableCard
                        key={l.id}
                        livrable={l}
                        onExportPdf={() => window.open(`/api/livrables/${l.id}/pdf`, "_blank")}
                        onEdit={() =>
                          setWorkspace({
                            action,
                            type: l.type,
                            existingLivrable: l,
                          })
                        }
                      />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* ────── DOCUMENT WORKSPACE (modal plein ecran) ────── */}
      {workspace && (
        <DocumentWorkspace
          action={workspace.action}
          livrableType={workspace.type}
          existingLivrable={workspace.existingLivrable}
          onClose={() => setWorkspace(null)}
          onLivrableReady={(livrable) => {
            // Mettre a jour la liste des livrables de l'action
            setActions((prev) =>
              prev.map((a) =>
                a.id === workspace.action.id
                  ? {
                      ...a,
                      livrables: [
                        ...(a.livrables || []).filter((l) => l.id !== livrable.id),
                        livrable,
                      ],
                    }
                  : a,
              ),
            );
          }}
        />
      )}

      {/* ────── 4. FORCE MAP ────── */}
      <section className="mb-8">
        <h2 className="mb-4 flex items-center gap-2 font-serif text-xl font-bold text-dark">
          <Shield className="h-5 w-5 text-warm" />
          Cartographie des forces
        </h2>

        {brief.force_map?.length > 0 && (
          <ForceMapChart groups={brief.force_map} />
        )}

        <div className="space-y-3">
          {brief.force_map?.map((g: ForceMapEntry) => {
            const cfg = positionConfig[g.position] || positionConfig.mixte;
            const analyseBullets = formatAnalyse(g.analyse);
            const isOpen = expandedGroups.has(g.groupe);
            return (
              <div
                key={g.groupe}
                className={`rounded-xl border-2 ${cfg.border} ${cfg.bg} transition-all`}
              >
                <button
                  onClick={() => toggleGroup(g.groupe)}
                  className="flex w-full items-center justify-between px-5 py-4 text-left"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-base font-bold text-dark">
                      {g.groupe}
                    </span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-semibold ${cfg.badge}`}
                    >
                      {cfg.label}
                    </span>
                    <span className="text-sm text-muted">
                      {g.nb_amendements} amdt{g.nb_amendements > 1 ? "s" : ""}
                      {g.nb_adoptes > 0 &&
                        ` \u2022 ${g.nb_adoptes} adopte${g.nb_adoptes > 1 ? "s" : ""}`}
                    </span>
                  </div>
                  {isOpen ? (
                    <ChevronUp className="h-4 w-4 text-muted" />
                  ) : (
                    <ChevronDown className="h-4 w-4 text-muted" />
                  )}
                </button>
                {isOpen && (
                  <div className="border-t border-current/10 px-5 pb-4 pt-3">
                    <ul className="space-y-2">
                      {analyseBullets.map((b, i) => (
                        <li
                          key={i}
                          className="flex gap-3 text-sm leading-relaxed text-dark/80"
                        >
                          <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-dark/30" />
                          <RichText text={b} />
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* ────── 5. ACTEURS CLES ENRICHIS ────── */}
      <section className="mb-8">
        <h2 className="mb-4 flex items-center gap-2 font-serif text-xl font-bold text-dark">
          <Phone className="h-5 w-5 text-warm" />
          Acteurs cles
        </h2>
        {acteursCles.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2">
            {acteursCles.map((ac, i) => (
              <div
                key={ac.uid || i}
                className="rounded-xl border border-border bg-white p-5 transition-shadow hover:shadow-md"
              >
                <div className="flex items-start justify-between">
                  <Link
                    href={`/dashboard/acteurs/${ac.uid}`}
                    className="group flex items-center gap-2"
                  >
                    <span className="text-lg font-bold text-dark group-hover:text-warm">
                      {ac.nom}
                    </span>
                    <ExternalLink className="h-3.5 w-3.5 text-muted opacity-0 transition-opacity group-hover:opacity-100" />
                  </Link>
                  <InfluenceGauge score={ac.influence_score} />
                </div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                  {ac.groupe && (
                    <span className="rounded bg-stone-100 px-2 py-0.5 font-semibold text-stone-700">
                      {ac.groupe}
                    </span>
                  )}
                  {ac.nb_amendements_dossier ? (
                    <span className="font-medium text-dark">
                      {ac.nb_amendements_dossier} amendement
                      {ac.nb_amendements_dossier > 1 ? "s" : ""} sur ce texte
                    </span>
                  ) : null}
                </div>
                {ac.why_relevant && (
                  <p className="mt-2 text-xs text-muted">{ac.why_relevant}</p>
                )}
                <div className="mt-3 flex gap-2">
                  <Link
                    href={`/dashboard/chat?prompt=Redige un email a ${ac.nom}&agent=redacteur&texte_uid=${texteUid}`}
                    className="inline-flex items-center gap-1 rounded bg-warm/10 px-2 py-1 text-xs font-medium text-warm hover:bg-warm/20"
                  >
                    Contacter
                  </Link>
                  <Link
                    href={`/dashboard/acteurs/${ac.uid}`}
                    className="inline-flex items-center gap-1 rounded bg-stone-100 px-2 py-1 text-xs font-medium text-stone-600 hover:bg-stone-200"
                  >
                    Voir fiche
                  </Link>
                </div>
              </div>
            ))}
          </div>
        ) : brief.key_contacts?.length ? (
          <div className="grid gap-4 sm:grid-cols-2">
            {brief.key_contacts.map((c: KeyContact, i: number) => {
              const whyBullets = formatAnalyse(c.why_relevant || "");
              return (
                <div
                  key={c.uid || i}
                  className="rounded-xl border border-border bg-white p-5"
                >
                  <Link
                    href={`/dashboard/acteurs/${c.uid}`}
                    className="group flex items-center gap-2"
                  >
                    <span className="text-lg font-bold text-dark group-hover:text-warm">
                      {c.nom}
                    </span>
                  </Link>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                    <span className="rounded bg-stone-100 px-2 py-0.5 font-semibold text-stone-700">
                      {c.groupe}
                    </span>
                    <span className="font-medium text-dark">
                      {c.nb_amendements} amendement{c.nb_amendements > 1 ? "s" : ""}
                    </span>
                    <span className="rounded bg-warm/10 px-2 py-0.5 font-bold text-warm">
                      {Math.round(c.taux_adoption * 100)}% adoption
                    </span>
                  </div>
                  <ul className="mt-3 space-y-1.5">
                    {whyBullets.map((b, j) => (
                      <li key={j} className="flex gap-2.5 text-sm leading-relaxed text-muted">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-stone-300" />
                        <RichText text={b} />
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        ) : null}
      </section>

      {/* ────── 6. TIMELINE ENRICHIE ────── */}
      <section className="mb-8">
        <h2 className="mb-4 flex items-center gap-2 font-serif text-xl font-bold text-dark">
          <Clock className="h-5 w-5 text-warm" />
          Timeline du dossier
        </h2>
        {evenements.length > 0 ? (
          <div className="rounded-xl border border-border bg-white p-5">
            <div className="space-y-0">
              {evenements.map((ev, i) => {
                const IconComp = eventIcons[ev.type] || Clock;
                const dotColor = severityColors[ev.severity] || "bg-stone-400";
                return (
                  <div key={ev.id} className="flex gap-3 py-2.5">
                    <div className="flex flex-col items-center">
                      <div className={`h-2.5 w-2.5 rounded-full ${dotColor}`} />
                      {i < evenements.length - 1 && (
                        <div className="mt-1 h-full w-px bg-border" />
                      )}
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <IconComp className="h-3.5 w-3.5 text-muted" />
                        <span className="rounded bg-stone-100 px-1.5 py-0.5 text-[10px] font-medium text-stone-500 uppercase">
                          {ev.type}
                        </span>
                        <p className="text-sm font-medium text-dark">{ev.title}</p>
                      </div>
                      {ev.description && (
                        <p className="mt-0.5 text-xs text-muted">{ev.description}</p>
                      )}
                      {ev.date && (
                        <p className="mt-0.5 text-xs text-muted">
                          {new Date(ev.date).toLocaleDateString("fr-FR", {
                            day: "numeric",
                            month: "long",
                            year: "numeric",
                          })}
                        </p>
                      )}
                    </div>
                    {ev.source_url && (
                      <a
                        href={ev.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-muted hover:text-warm"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-border bg-cream/50 p-6 text-center text-sm text-muted">
            Aucun evenement disponible.
          </div>
        )}
      </section>

      {/* ────── PLAN D'ACTION (from brief) ────── */}
      {brief.action_plan?.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-4 flex items-center gap-2 font-serif text-xl font-bold text-dark">
            <ClipboardList className="h-5 w-5 text-warm" />
            Plan d&apos;action (brief)
          </h2>
          <div className="space-y-3">
            {brief.action_plan.map((p: ActionPlanItem, i: number) => (
              <div
                key={i}
                className="flex gap-4 rounded-xl border border-border bg-white p-5"
              >
                <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-full bg-warm text-sm font-bold text-white">
                  {p.priority || i + 1}
                </div>
                <div className="flex-1">
                  <p className="text-sm font-medium leading-relaxed text-dark">
                    {p.action}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-3 text-xs">
                    {p.deadline && (
                      <span className="flex items-center gap-1 rounded bg-stone-100 px-2 py-0.5 font-medium text-stone-600">
                        <Target className="h-3 w-3" />
                        {p.deadline}
                      </span>
                    )}
                    {p.who && (
                      <span className="flex items-center gap-1 rounded bg-warm/10 px-2 py-0.5 font-medium text-warm">
                        <Users className="h-3 w-3" />
                        {p.who}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ────── CHAT CONTEXTUEL ────── */}
      <DossierChat
        texteUid={texteUid}
        texteTitle={brief.texte?.titre}
      />
    </div>
  );
}
