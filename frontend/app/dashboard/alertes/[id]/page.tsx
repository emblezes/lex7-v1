"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Loader2,
  ExternalLink,
  Users,
  FileText,
  Mail,
  Eye,
  Check,
  Clock,
  MessageSquare,
  PenTool,
} from "lucide-react";
import {
  fetchAlerte,
  fetchTexte,
  updateActionStatus,
  type ImpactAlert,
  type Texte,
  type AdoptionBreakdown,
  type AlertAction,
} from "@/lib/api";

function capitalize(text: string | null | undefined): string {
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function cleanHtml(html: string | null | undefined): string {
  if (!html) return "";
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

const levelLabels: Record<string, { color: string; label: string }> = {
  critical: { color: "bg-threat text-white", label: "CRITIQUE" },
  high: { color: "bg-warning text-white", label: "ÉLEVÉ" },
  medium: { color: "bg-info text-white", label: "MOYEN" },
  low: { color: "bg-muted/20 text-muted", label: "FAIBLE" },
};

const sortLabels: Record<string, { color: string; label: string }> = {
  Adopté: { color: "bg-success/10 text-success", label: "Adopté" },
  Rejeté: { color: "bg-threat/10 text-threat", label: "Rejeté" },
  Retiré: { color: "bg-muted/20 text-muted", label: "Retiré" },
  Tombé: { color: "bg-muted/20 text-muted", label: "Tombé" },
  "Non soutenu": { color: "bg-muted/20 text-muted", label: "Non soutenu" },
};

const actionTypeIcons: Record<string, typeof FileText> = {
  draft_note: FileText,
  draft_email: Mail,
  draft_amendment: PenTool,
  monitor: Eye,
};

const actionTypeLabels: Record<string, string> = {
  draft_note: "Rédiger une note",
  draft_email: "Rédiger un email",
  draft_amendment: "Rédiger un amendement",
  monitor: "Surveillance",
};

/* ── Impact line with clickable links ── */

import type { AlertAmendement } from "@/lib/api";

function ImpactLine({
  text,
  amdt,
  texteUid,
}: {
  text: string;
  amdt?: AlertAmendement;
  texteUid?: string | null;
}) {
  // "Porteur : Nom Prenom" → link to acteur page
  if (text.startsWith("Porteur :") && amdt?.auteur?.uid) {
    const name = text.replace("Porteur :", "").trim();
    return (
      <span>
        Porteur :{" "}
        <Link
          href={`/dashboard/acteurs/${amdt.auteur.uid}`}
          className="font-semibold text-warm hover:underline"
        >
          {name}
        </Link>
      </span>
    );
  }

  // "Article cible : Article 12" → link to texte page
  if (text.startsWith("Article cible :") && texteUid) {
    const article = text.replace("Article cible :", "").trim();
    return (
      <span>
        Article cible :{" "}
        <Link
          href={`/dashboard/textes/${texteUid}`}
          className="font-semibold text-warm hover:underline"
        >
          {article}
        </Link>
      </span>
    );
  }

  // "Amendement XXX (...)" → link to scroll to amendement section
  if (text.match(/^Amendement\s/) && amdt?.uid) {
    // Extract the amendement number part before the colon
    const colonIdx = text.indexOf(":");
    const prefix = colonIdx >= 0 ? text.slice(0, colonIdx) : text;
    const rest = colonIdx >= 0 ? text.slice(colonIdx) : "";

    return (
      <span>
        <Link
          href={amdt.url_source || `#amendement`}
          target={amdt.url_source ? "_blank" : undefined}
          rel={amdt.url_source ? "noopener noreferrer" : undefined}
          className="font-semibold text-warm hover:underline"
        >
          {prefix}
        </Link>
        {rest}
      </span>
    );
  }

  return <span>{capitalize(text)}</span>;
}

/* ── Adoption Gauge ── */

function AdoptionGauge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 60 ? "text-success" : pct >= 35 ? "text-warning" : "text-threat";

  return (
    <div className="flex flex-col items-center gap-2">
      <div className="relative h-20 w-20">
        <svg className="h-20 w-20 -rotate-90" viewBox="0 0 36 36">
          <path
            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            className="text-border"
          />
          <path
            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            strokeDasharray={`${pct}, 100`}
            className={color}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={`text-lg font-bold ${color}`}>{pct}%</span>
        </div>
      </div>
      <span className="text-xs font-medium text-muted">
        Probabilité d&apos;adoption
      </span>
    </div>
  );
}

/* ── Score breakdown — descriptive text ── */

function ScoreExplanation({
  breakdown,
  auteurName,
  groupeName,
}: {
  breakdown: AdoptionBreakdown;
  auteurName?: string | null;
  groupeName?: string | null;
}) {
  const pct = Math.round(breakdown.score * 100);
  const color =
    pct >= 60 ? "text-success" : pct >= 35 ? "text-warning" : "text-threat";

  // Build explanation sentences
  const sentences: string[] = [];

  // Overall assessment
  if (pct >= 70) sentences.push(`La probabilité d'adoption est élevée (${pct}%).`);
  else if (pct >= 50) sentences.push(`La probabilité d'adoption est modérée (${pct}%).`);
  else if (pct >= 25) sentences.push(`La probabilité d'adoption est faible (${pct}%).`);
  else sentences.push(`La probabilité d'adoption est très faible (${pct}%).`);

  // Auteur factor
  const auteurPct = Math.round(breakdown.auteur.rate * 100);
  const who = auteurName || "L'auteur";
  if (breakdown.auteur.total > 0) {
    if (auteurPct === 0) {
      sentences.push(
        `${who} n'a fait adopter aucun de ses ${breakdown.auteur.total} amendements déposés.`,
      );
    } else if (auteurPct >= 50) {
      sentences.push(
        `${who} a un bon taux d'adoption : ${breakdown.auteur.adopted} adoptés sur ${breakdown.auteur.total} déposés (${auteurPct}%).`,
      );
    } else {
      sentences.push(
        `${who} a fait adopter ${breakdown.auteur.adopted} de ses ${breakdown.auteur.total} amendements (${auteurPct}%).`,
      );
    }
  } else {
    sentences.push(`${who} n'a pas d'historique d'amendements.`);
  }

  // Groupe factor
  const groupePct = Math.round(breakdown.groupe.rate * 100);
  const grp = groupeName ? `Le groupe ${groupeName}` : "Son groupe politique";
  if (breakdown.groupe.total > 0) {
    if (groupePct <= 5) {
      sentences.push(
        `${grp} a un taux d'adoption de seulement ${groupePct}% (${breakdown.groupe.adopted}/${breakdown.groupe.total}).`,
      );
    } else if (groupePct >= 40) {
      sentences.push(
        `${grp} a un taux d'adoption favorable de ${groupePct}% (${breakdown.groupe.adopted}/${breakdown.groupe.total}).`,
      );
    } else {
      sentences.push(
        `${grp} a un taux d'adoption de ${groupePct}% (${breakdown.groupe.adopted}/${breakdown.groupe.total}).`,
      );
    }
  }

  // Commission factor
  const commPct = Math.round(breakdown.commission.rate * 100);
  if (breakdown.commission.total > 0) {
    sentences.push(
      `La commission adopte ${commPct}% des amendements examinés (${breakdown.commission.adopted}/${breakdown.commission.total}).`,
    );
  }

  // Gouvernement factor
  if (breakdown.gouvernement.is_gouvernement) {
    sentences.push(
      "C'est un amendement gouvernemental, ce qui augmente fortement sa probabilité d'adoption.",
    );
  }

  const [headline, ...details] = sentences;

  return (
    <div className="mt-4">
      <p className={`text-sm font-bold ${color}`}>{headline}</p>
      {details.length > 0 && (
        <ul className="mt-2 space-y-1">
          {details.map((s, i) => (
            <li key={i} className="flex items-start gap-2 text-sm leading-relaxed text-dark">
              <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-muted/50" />
              {s}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ── Action item with agent button ── */

function ActionItem({
  action,
  index,
  status,
  alertId,
  onStatusChange,
}: {
  action: AlertAction;
  index: number;
  status: string;
  alertId: number;
  onStatusChange: (index: number, status: string) => void;
}) {
  const router = useRouter();
  const Icon = actionTypeIcons[action.type] || FileText;
  const isDone = status === "done";
  const isInProgress = status === "in_progress";

  const handleToggle = async () => {
    const newStatus = isDone ? "pending" : "done";
    try {
      await updateActionStatus(alertId, index, newStatus);
      onStatusChange(index, newStatus);
    } catch (e) {
      console.error("Failed to update action status", e);
    }
  };

  const handleActivate = () => {
    if (!action.agent_prompt) return;
    const encodedPrompt = encodeURIComponent(action.agent_prompt);
    router.push(`/dashboard/chat?prompt=${encodedPrompt}`);
  };

  return (
    <div
      className={`flex items-start gap-3 rounded-lg border p-3 transition-all ${
        isDone
          ? "border-success/30 bg-success/5"
          : isInProgress
            ? "border-warning/30 bg-warning/5"
            : "border-border bg-white"
      }`}
    >
      {/* Checkbox */}
      <button
        onClick={handleToggle}
        className={`mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded border transition-all ${
          isDone
            ? "border-success bg-success text-white"
            : "border-border hover:border-warm"
        }`}
      >
        {isDone && <Check className="h-3 w-3" />}
      </button>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <Icon className="h-3.5 w-3.5 flex-shrink-0 text-muted" />
          <span className="text-xs font-medium uppercase tracking-wider text-muted">
            {actionTypeLabels[action.type] || action.type}
          </span>
          {isDone && (
            <span className="rounded-full bg-success/10 px-2 py-0.5 text-[10px] font-bold text-success">
              Fait
            </span>
          )}
          {isInProgress && (
            <span className="rounded-full bg-warning/10 px-2 py-0.5 text-[10px] font-bold text-warning">
              En cours
            </span>
          )}
        </div>
        <p
          className={`mt-1 text-sm ${isDone ? "text-muted line-through" : "text-dark"}`}
        >
          {action.label}
        </p>
      </div>

      {/* Agent button */}
      {action.agent_prompt && !isDone && (
        <button
          onClick={handleActivate}
          className="flex flex-shrink-0 items-center gap-1.5 rounded-lg bg-warm px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-warm/90"
        >
          <MessageSquare className="h-3.5 w-3.5" />
          Activer
        </button>
      )}
    </div>
  );
}

/* ── Main page ── */

export default function AlertDetailPage() {
  const params = useParams();
  const alertId = Number(params.id);
  const [alert, setAlert] = useState<ImpactAlert | null>(null);
  const [texte, setTexte] = useState<Texte | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionsStatus, setActionsStatus] = useState<Record<string, string>>(
    {},
  );

  useEffect(() => {
    if (!alertId) return;
    fetchAlerte(alertId)
      .then(async (a) => {
        setAlert(a);
        setActionsStatus(a.actions_status || {});
        if (a.texte_uid) {
          try {
            const t = await fetchTexte(a.texte_uid);
            setTexte(t);
          } catch {
            /* texte not found */
          }
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [alertId]);

  const handleActionStatusChange = (index: number, status: string) => {
    setActionsStatus((prev) => ({ ...prev, [String(index)]: status }));
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-warm" />
      </div>
    );
  }

  if (!alert) {
    return <p className="text-muted">Alerte non trouvée.</p>;
  }

  const level = levelLabels[alert.impact_level] || levelLabels.medium;
  const sourceLabel = texte?.source_label || texte?.source || "";
  const amdt = alert.amendement;

  const auteurName = amdt?.auteur
    ? `${amdt.auteur.prenom} ${amdt.auteur.nom}`
    : amdt?.auteur_nom || null;
  const auteurGroupe =
    amdt?.auteur?.groupe_politique?.libelle_court ||
    amdt?.groupe?.libelle_court ||
    amdt?.groupe_nom ||
    null;

  // Count completed actions
  const totalActions = alert.actions?.length || 0;
  const doneActions = Object.values(actionsStatus).filter(
    (s) => s === "done",
  ).length;

  return (
    <div className="space-y-6">
      {/* Top bar */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          <Link
            href="/dashboard/alertes"
            className="flex items-center gap-1 text-sm text-muted hover:text-dark"
          >
            <ArrowLeft className="h-4 w-4" />
            Retour
          </Link>
          <span
            className={`rounded-full px-3 py-1 text-xs font-bold ${level.color}`}
          >
            {level.label}
          </span>
          {alert.is_threat !== false ? (
            <span className="rounded-full bg-threat/10 px-3 py-1 text-xs font-medium text-threat">
              Menace
            </span>
          ) : (
            <span className="rounded-full bg-success/10 px-3 py-1 text-xs font-medium text-success">
              Opportunité
            </span>
          )}
        </div>
        {alert.exposure_eur != null && alert.exposure_eur > 0 && (
          <div className="text-right">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted">
              Exposition estimée
            </p>
            <p className="font-serif text-3xl font-bold text-dark">
              {alert.exposure_eur.toLocaleString("fr-FR")}&nbsp;&euro;
            </p>
          </div>
        )}
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        {/* LEFT column (60%) */}
        <div className="space-y-6 lg:col-span-3">
          {/* Analyse d'impact */}
          <div className="rounded-xl bg-white p-6">
            <h2 className="mb-4 font-serif text-lg font-semibold text-dark">
              Analyse d&apos;impact
            </h2>
            {alert.impact_summary?.includes("\n") ? (
              <ul className="space-y-2">
                {alert.impact_summary.split("\n").filter(Boolean).map((line, i) => {
                  const text = line.replace(/^[•\-]\s*/, "").trim();
                  return (
                    <li key={i} className="flex items-start gap-2 text-sm leading-relaxed text-dark">
                      <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-warm" />
                      <ImpactLine text={text} amdt={amdt} texteUid={alert.texte_uid} />
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="text-sm leading-relaxed text-dark">
                {capitalize(alert.impact_summary)}
              </p>
            )}
          </div>

          {/* ── Amendement detail ── */}
          {amdt && (
            <div className="rounded-xl bg-white p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="font-serif text-lg font-semibold text-dark">
                  Amendement {amdt.numero}
                </h2>
                {amdt.sort && sortLabels[amdt.sort] && (
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-bold ${sortLabels[amdt.sort].color}`}
                  >
                    {sortLabels[amdt.sort].label}
                  </span>
                )}
                {!amdt.sort && amdt.etat && (
                  <span className="rounded-full bg-info/10 px-3 py-1 text-xs font-medium text-info">
                    {amdt.etat}
                  </span>
                )}
              </div>

              {amdt.article_vise && (
                <p className="mb-3 text-sm text-muted">
                  Vise :{" "}
                  <span className="font-medium text-dark">
                    {amdt.article_vise}
                  </span>
                </p>
              )}

              {amdt.resume_ia && (
                <div className="mb-4 rounded-lg bg-cream/50 p-4">
                  <p className="text-sm leading-relaxed text-dark">
                    {capitalize(amdt.resume_ia)}
                  </p>
                </div>
              )}

              {!amdt.resume_ia && amdt.expose_sommaire && (
                <div className="mb-4 rounded-lg bg-cream/50 p-4">
                  <p className="text-sm leading-relaxed text-dark">
                    {capitalize(
                      cleanHtml(amdt.expose_sommaire).slice(0, 500),
                    )}
                    {cleanHtml(amdt.expose_sommaire).length > 500 ? "..." : ""}
                  </p>
                </div>
              )}

              {/* Auteur + Groupe */}
              {auteurName && (
                <div className="mb-4 flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-warm/10">
                    <Users className="h-5 w-5 text-warm" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-dark">
                      {amdt.auteur?.uid ? (
                        <Link
                          href={`/dashboard/acteurs/${amdt.auteur.uid}`}
                          className="transition-colors hover:text-warm"
                        >
                          {auteurName}
                        </Link>
                      ) : (
                        auteurName
                      )}
                    </p>
                    {auteurGroupe && (
                      <p className="text-xs text-muted">{auteurGroupe}</p>
                    )}
                    {amdt.auteur_stats && (
                      <p className="text-xs text-muted">
                        {amdt.auteur_stats.nb_amendements} amendements déposés
                        {" · "}
                        {amdt.auteur_stats.taux_adoption}% adoptés
                      </p>
                    )}
                  </div>
                </div>
              )}

              {amdt.themes.length > 0 && (
                <div className="mb-4 flex flex-wrap gap-1.5">
                  {amdt.themes.map((theme) => (
                    <span
                      key={theme}
                      className="rounded-full bg-cream px-2.5 py-0.5 text-xs font-medium text-warm"
                    >
                      {theme}
                    </span>
                  ))}
                </div>
              )}

              {amdt.url_source && (
                <a
                  href={amdt.url_source}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs font-medium text-warm hover:underline"
                >
                  <ExternalLink className="h-3 w-3" />
                  Voir l&apos;amendement sur le site officiel
                </a>
              )}
            </div>
          )}

          {/* ── Cosignataires et coalitions ── */}
          {amdt && amdt.cosignataires.length > 0 && (
            <div className="rounded-xl bg-white p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="font-serif text-lg font-semibold text-dark">
                  Cosignataires ({amdt.cosignataires.length})
                </h2>
                {amdt.convergence_transpartisane && (
                  <span className="rounded-full bg-success/10 px-3 py-1 text-xs font-bold text-success">
                    Convergence transpartisane
                  </span>
                )}
              </div>
              {amdt.nb_groupes_differents > 1 && (
                <p className="mb-3 text-xs text-muted">
                  {amdt.nb_groupes_differents} groupes politiques différents
                  {amdt.convergence_transpartisane
                    ? " — signal fort de consensus"
                    : ""}
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                {amdt.cosignataires.map((c) => (
                  <Link
                    key={c.uid}
                    href={`/dashboard/acteurs/${c.uid}`}
                    className="flex items-center gap-2 rounded-lg bg-cream/50 px-3 py-2 text-xs transition-colors hover:bg-cream"
                  >
                    <span className="font-medium text-dark">
                      {c.prenom} {c.nom}
                    </span>
                    {c.groupe_politique?.libelle_court && (
                      <span className="text-muted">
                        {c.groupe_politique.libelle_court}
                      </span>
                    )}
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* Texte source */}
          {texte && (
            <Link
              href={`/dashboard/textes/${texte.uid}`}
              className="block rounded-xl bg-white p-6 transition-shadow hover:shadow-md"
            >
              <div className="mb-4 flex items-center justify-between">
                <h2 className="font-serif text-lg font-semibold text-dark">
                  Texte source
                </h2>
                <span className="flex items-center gap-1 text-xs font-medium text-warm">
                  Voir le texte complet &rarr;
                </span>
              </div>
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex rounded-full bg-warm/10 px-2.5 py-0.5 text-xs font-bold text-warm">
                    {texte.type_libelle || texte.type_code}
                  </span>
                  <span className="text-xs text-muted">{sourceLabel}</span>
                  {texte.amendements_count != null &&
                    texte.amendements_count > 0 && (
                      <span className="text-xs font-medium text-dark">
                        {texte.amendements_count} amendements
                      </span>
                    )}
                </div>
                <h3 className="font-serif text-base font-semibold text-dark">
                  {capitalize(texte.titre_court || texte.titre)}
                </h3>
                {texte.resume_ia && (
                  <p className="line-clamp-3 text-sm leading-relaxed text-muted">
                    {capitalize(texte.resume_ia)}
                  </p>
                )}
                {texte.date_depot && (
                  <p className="text-xs text-muted">
                    {new Date(texte.date_depot).toLocaleDateString("fr-FR", {
                      day: "numeric",
                      month: "long",
                      year: "numeric",
                    })}
                  </p>
                )}
              </div>
            </Link>
          )}

          {texte?.url_source && (
            <a
              href={texte.url_source}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 rounded-xl border border-border bg-white p-4 text-sm font-medium text-warm transition-colors hover:bg-cream"
            >
              <ExternalLink className="h-4 w-4" />
              Lire le texte intégral sur {sourceLabel}
            </a>
          )}
        </div>

        {/* RIGHT column (40%) */}
        <div className="space-y-6 lg:col-span-2">
          {/* Score adoption + breakdown */}
          {amdt?.adoption_score != null && (
            <div className="rounded-xl bg-white p-6">
              <h2 className="mb-4 font-serif text-lg font-semibold text-dark">
                Probabilité d&apos;adoption
              </h2>
              <div className="flex items-center justify-center">
                <AdoptionGauge score={amdt.adoption_score} />
              </div>
              {amdt.sort && (
                <p className="mt-3 text-center text-xs text-muted">
                  Résultat effectif :{" "}
                  <span className="font-semibold text-dark">{amdt.sort}</span>
                </p>
              )}
              {amdt.convergence_transpartisane && (
                <p className="mt-2 text-center text-xs text-success">
                  Soutien transpartisan ({amdt.nb_groupes_differents} groupes)
                </p>
              )}

              {/* Score explanation */}
              {amdt.adoption_breakdown && (
                <ScoreExplanation
                  breakdown={amdt.adoption_breakdown}
                  auteurName={auteurName}
                  groupeName={auteurGroupe}
                />
              )}
            </div>
          )}

          {/* ── Actions recommandées (structured) ── */}
          {alert.actions && alert.actions.length > 0 && (
            <div className="rounded-xl bg-white p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="font-serif text-lg font-semibold text-dark">
                  Actions recommandées
                </h2>
                {totalActions > 0 && (
                  <span className="text-xs text-muted">
                    {doneActions}/{totalActions} terminée
                    {doneActions > 1 ? "s" : ""}
                  </span>
                )}
              </div>

              {/* Progress bar */}
              {totalActions > 0 && (
                <div className="mb-4 h-1.5 w-full rounded-full bg-border">
                  <div
                    className="h-1.5 rounded-full bg-success transition-all"
                    style={{
                      width: `${Math.round((doneActions / totalActions) * 100)}%`,
                    }}
                  />
                </div>
              )}

              <div className="space-y-3">
                {alert.actions.map((action, idx) => (
                  <ActionItem
                    key={idx}
                    action={action}
                    index={idx}
                    status={actionsStatus[String(idx)] || "pending"}
                    alertId={alert.id}
                    onStatusChange={handleActionStatusChange}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Thèmes matchés */}
          <div className="rounded-xl bg-white p-6">
            <h2 className="mb-4 font-serif text-lg font-semibold text-dark">
              Thèmes identifiés
            </h2>
            {alert.matched_themes.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {alert.matched_themes.map((theme) => (
                  <span
                    key={theme}
                    className="rounded-full bg-cream px-3 py-1 text-sm font-medium text-warm"
                  >
                    {theme}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted">Aucun thème identifié.</p>
            )}
          </div>

          {/* Informations */}
          <div className="rounded-xl bg-white p-6">
            <h2 className="mb-4 font-serif text-lg font-semibold text-dark">
              Informations
            </h2>
            <dl className="space-y-3 text-sm">
              {alert.created_at && (
                <div className="flex justify-between">
                  <dt className="text-muted">Date de l&apos;alerte</dt>
                  <dd className="text-dark">
                    {new Date(alert.created_at).toLocaleDateString("fr-FR", {
                      day: "numeric",
                      month: "long",
                      year: "numeric",
                    })}
                  </dd>
                </div>
              )}
              {texte && (
                <div className="flex justify-between">
                  <dt className="text-muted">Chambre</dt>
                  <dd className="text-dark">{sourceLabel}</dd>
                </div>
              )}
              {texte?.commission && (
                <div className="flex justify-between gap-2">
                  <dt className="flex-shrink-0 text-muted">Commission</dt>
                  <dd className="text-right text-xs text-dark">
                    {texte.commission.libelle_court || texte.commission.libelle}
                  </dd>
                </div>
              )}
              {amdt?.date_depot && (
                <div className="flex justify-between">
                  <dt className="text-muted">Dépôt amendement</dt>
                  <dd className="text-dark">
                    {new Date(amdt.date_depot).toLocaleDateString("fr-FR", {
                      day: "numeric",
                      month: "long",
                      year: "numeric",
                    })}
                  </dd>
                </div>
              )}
              {amdt?.etat && (
                <div className="flex justify-between">
                  <dt className="text-muted">État</dt>
                  <dd className="text-dark">{amdt.etat}</dd>
                </div>
              )}
            </dl>
          </div>
        </div>
      </div>
    </div>
  );
}
