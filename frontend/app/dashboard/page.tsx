"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  TrendingUp,
  Euro,
  Loader2,
  Shield,
  Inbox,
} from "lucide-react";
import {
  fetchDashboard,
  fetchTextesSuivis,
  fetchProfileAlertes,
  fetchSignaux,
  fetchActions,
  type DashboardData,
  type TexteBrief,
  type ImpactAlert,
  type Signal,
  type ActionTask,
} from "@/lib/api";
import { useProfile } from "./ProfileContext";
import { formatEur } from "@/components/utils";
import ActionCard from "@/components/ActionCard";
import TimelineEvent, { type TimelineItem } from "@/components/TimelineEvent";
import EmptyState from "@/components/EmptyState";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isRecent(iso: string | null, hoursAgo: number): boolean {
  if (!iso) return false;
  return Date.now() - new Date(iso).getTime() < hoursAgo * 3_600_000;
}

// Derive top 3 actions from briefs + alerts
function deriveTopActions(
  briefs: TexteBrief[],
  alerts: ImpactAlert[],
): { priority: number; label: string; type?: string; deadline?: string; who?: string; href?: string; rationale?: string }[] {
  const items: { priority: number; label: string; type?: string; deadline?: string; who?: string; href?: string; rationale?: string; sortKey: number }[] = [];

  // From briefs action plans (priority <= 2)
  for (const b of briefs) {
    if (!b.action_plan) continue;
    for (const ap of b.action_plan) {
      if (ap.priority <= 2) {
        const severityWeight = b.impact_level === "critical" ? 4 : b.impact_level === "high" ? 3 : b.impact_level === "medium" ? 2 : 1;
        items.push({
          priority: ap.priority,
          label: ap.action,
          deadline: ap.deadline,
          who: ap.who,
          href: `/dashboard/dossiers/${b.texte_uid}`,
          rationale: b.texte?.titre,
          sortKey: severityWeight * 10 + (10 - ap.priority),
        });
      }
    }
  }

  // From recent critical/high alerts actions
  const recentAlerts = alerts.filter(
    (a) => (a.impact_level === "critical" || a.impact_level === "high") && isRecent(a.created_at, 48),
  );
  for (const alert of recentAlerts) {
    for (const action of alert.actions || []) {
      const severityWeight = alert.impact_level === "critical" ? 4 : 3;
      items.push({
        priority: 1,
        label: action.label,
        type: action.type,
        href: `/dashboard/alertes/${alert.id}`,
        rationale: alert.impact_summary?.split(".")[0],
        sortKey: severityWeight * 10 + 5,
      });
    }
  }

  // Sort by sortKey desc and take top 3
  items.sort((a, b) => b.sortKey - a.sortKey);
  return items.slice(0, 3).map((item, i) => ({
    priority: i + 1,
    label: item.label,
    type: item.type,
    deadline: item.deadline,
    who: item.who,
    href: item.href,
    rationale: item.rationale,
  }));
}

// Build unified timeline
function buildTimeline(
  alerts: ImpactAlert[],
  dashboard: DashboardData | null,
  signaux: Signal[],
  briefs: TexteBrief[],
): TimelineItem[] {
  const items: TimelineItem[] = [];

  // Alerts
  for (const a of alerts) {
    items.push({
      id: `alert-${a.id}`,
      type: "alert",
      date: a.created_at,
      summary: a.impact_summary?.split(".")[0] || "Nouvelle alerte",
      tags: a.matched_themes?.slice(0, 2),
      href: `/dashboard/alertes/${a.id}`,
      dotColor: a.is_threat ? "bg-red-500" : "bg-emerald-500",
    });
  }

  // Recent textes from dashboard
  if (dashboard?.recent_textes) {
    for (const t of dashboard.recent_textes.slice(0, 5)) {
      items.push({
        id: `texte-${t.uid}`,
        type: "texte",
        date: t.created_at || t.date_depot,
        summary: t.titre_court || t.titre || t.uid,
        tags: t.themes?.slice(0, 2),
        href: `/dashboard/dossiers/${t.uid}`,
      });
    }
  }

  // Reunions
  if (dashboard?.upcoming_reunions) {
    for (const r of dashboard.upcoming_reunions.slice(0, 3) as Array<{
      uid: string; date_debut: string; organe_ref: string; etat: string;
    }>) {
      items.push({
        id: `reunion-${r.uid}`,
        type: "reunion",
        date: r.date_debut,
        summary: `Reunion ${r.organe_ref} — ${r.etat}`,
      });
    }
  }

  // Signaux
  for (const s of signaux) {
    items.push({
      id: `signal-${s.id}`,
      type: "signal",
      date: s.created_at,
      summary: s.title || s.description,
      tags: s.themes?.slice(0, 2),
    });
  }

  // Change logs from briefs
  for (const b of briefs) {
    const logs = b.followup?.change_log;
    if (Array.isArray(logs)) {
      for (const log of logs as Array<{ date: string; event: string; detail: string }>) {
        items.push({
          id: `change-${b.texte_uid}-${log.date}`,
          type: "change",
          date: log.date,
          summary: `${log.event} — ${log.detail}`,
          href: `/dashboard/dossiers/${b.texte_uid}`,
        });
      }
    }
  }

  // Sort by date desc
  items.sort((a, b) => {
    const da = a.date ? new Date(a.date).getTime() : 0;
    const db = b.date ? new Date(b.date).getTime() : 0;
    return db - da;
  });

  return items.slice(0, 20);
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AujourdhuiPage() {
  const { activeProfile, profileDetail, loading: profileLoading } = useProfile();
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [briefs, setBriefs] = useState<TexteBrief[]>([]);
  const [alerts, setAlerts] = useState<ImpactAlert[]>([]);
  const [signaux, setSignaux] = useState<Signal[]>([]);
  const [realActions, setRealActions] = useState<ActionTask[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (profileLoading) return;
    if (!activeProfile) {
      setLoading(false);
      return;
    }

    setLoading(true);
    Promise.all([
      fetchTextesSuivis(activeProfile.id),
      fetchProfileAlertes(activeProfile.id, { limit: 50 }),
      fetchDashboard().catch(() => null),
      fetchSignaux({ limit: 10 }).catch(() => []),
      fetchActions({ status: "pending" }).catch(() => []),
    ])
      .then(([texteBriefs, alertsData, dash, sig, acts]) => {
        setBriefs(texteBriefs);
        setAlerts(alertsData);
        if (dash) setDashboard(dash);
        setSignaux(sig as Signal[]);
        setRealActions(acts as ActionTask[]);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [activeProfile, profileLoading]);

  // Derive data
  const threats24h = useMemo(
    () => alerts.filter((a) => a.is_threat && isRecent(a.created_at, 24)),
    [alerts],
  );
  const opps24h = useMemo(
    () => alerts.filter((a) => !a.is_threat && isRecent(a.created_at, 24)),
    [alerts],
  );
  const totalExposure = useMemo(
    () => briefs.reduce((sum, b) => sum + (b.exposure_eur || 0), 0),
    [briefs],
  );
  const topActions = useMemo(
    () => deriveTopActions(briefs, alerts),
    [briefs, alerts],
  );
  const timeline = useMemo(
    () => buildTimeline(alerts, dashboard, signaux, briefs),
    [alerts, dashboard, signaux, briefs],
  );

  if (loading || profileLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-warm" />
      </div>
    );
  }

  if (!activeProfile || !profileDetail) {
    return (
      <div className="flex h-64 items-center justify-center text-muted">
        Selectionnez un client pour voir le tableau de bord.
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="font-serif text-3xl font-bold text-dark">
          Aujourd&apos;hui
        </h1>
        <p className="mt-1 text-sm text-muted">
          <Shield className="mr-1 inline h-3.5 w-3.5" />
          {profileDetail.name} — {profileDetail.sectors.join(", ")}
        </p>
      </div>

      {/* Module A — Resume quotidien */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-xl bg-red-600 p-5 text-white">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider opacity-80">
              MENACES 24H
            </span>
            <AlertTriangle className="h-5 w-5 opacity-60" />
          </div>
          <div className="mt-2 text-3xl font-bold">{threats24h.length}</div>
          <p className="mt-1 text-xs opacity-70">
            nouvelle{threats24h.length !== 1 ? "s" : ""} alerte{threats24h.length !== 1 ? "s" : ""} menace
          </p>
        </div>
        <div className="rounded-xl bg-emerald-600 p-5 text-white">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider opacity-80">
              OPPORTUNITES 24H
            </span>
            <TrendingUp className="h-5 w-5 opacity-60" />
          </div>
          <div className="mt-2 text-3xl font-bold">{opps24h.length}</div>
          <p className="mt-1 text-xs opacity-70">
            nouvelle{opps24h.length !== 1 ? "s" : ""} opportunite{opps24h.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="rounded-xl bg-white p-5 text-dark border border-border">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted">
              EXPOSITION TOTALE
            </span>
            <Euro className="h-5 w-5 text-muted" />
          </div>
          <div className="mt-2 text-3xl font-bold">{formatEur(totalExposure)}</div>
          <p className="mt-1 text-xs text-muted">
            sur {briefs.length} dossier{briefs.length !== 1 ? "s" : ""} actif{briefs.length !== 1 ? "s" : ""}
          </p>
        </div>
      </div>

      {/* Module B — Prochaines actions (reelles depuis le backend) */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-serif text-xl font-semibold text-dark">
            Prochaines actions
          </h2>
          <Link
            href="/dashboard/actions"
            className="text-sm font-medium text-warm hover:text-dark"
          >
            Tout voir
          </Link>
        </div>

        {realActions.length === 0 && topActions.length === 0 ? (
          <EmptyState
            icon={Inbox}
            title="Aucune action prioritaire"
            description="Vos agents analysent l'actualite. Les actions apparaitront des qu'un texte vous concerne."
          />
        ) : realActions.length > 0 ? (
          <div className="space-y-3">
            {realActions.slice(0, 5).map((action) => (
              <ActionCard
                key={action.id}
                priority={action.priority || 3}
                label={action.label}
                type={action.action_type}
                deadline={action.due_date || undefined}
                href={action.texte_uid ? `/dashboard/dossiers/${action.texte_uid}` : `/dashboard/actions`}
                rationale={action.rationale || undefined}
              />
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            {topActions.map((action, i) => (
              <ActionCard
                key={i}
                priority={action.priority}
                label={action.label}
                type={action.type}
                deadline={action.deadline}
                who={action.who}
                href={action.href}
                rationale={action.rationale}
              />
            ))}
          </div>
        )}
      </div>

      {/* Module D — Dossiers chauds */}
      {briefs.length > 0 && (
        <div>
          <h2 className="mb-4 font-serif text-xl font-semibold text-dark">
            Dossiers chauds
          </h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {[...briefs]
              .sort((a, b) => {
                const levelOrder: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 };
                return (levelOrder[b.impact_level] || 0) - (levelOrder[a.impact_level] || 0);
              })
              .slice(0, 3)
              .map((b) => (
                <Link
                  key={b.id}
                  href={`/dashboard/dossiers/${b.texte_uid}`}
                  className="rounded-xl border border-border bg-white p-4 transition-shadow hover:shadow-md"
                >
                  <div className="flex items-center gap-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-bold ${
                      b.impact_level === "critical" ? "bg-red-100 text-red-700" :
                      b.impact_level === "high" ? "bg-amber-100 text-amber-700" :
                      "bg-stone-100 text-stone-600"
                    }`}>
                      {b.impact_level}
                    </span>
                    <span className={`text-xs ${b.is_threat ? "text-red-600" : "text-emerald-600"}`}>
                      {b.is_threat ? "Menace" : "Opportunite"}
                    </span>
                  </div>
                  <p className="mt-2 text-sm font-semibold text-dark line-clamp-2">
                    {b.texte?.titre || b.texte_uid}
                  </p>
                  <div className="mt-2 flex items-center gap-3 text-xs text-muted">
                    {b.exposure_eur ? (
                      <span className="font-bold text-dark">{formatEur(b.exposure_eur)}</span>
                    ) : null}
                    <span>{b.nb_amendements_analyzed} amdts</span>
                    <span>{b.nb_groupes} groupes</span>
                  </div>
                </Link>
              ))}
          </div>
        </div>
      )}

      {/* Module C — Timeline */}
      <div>
        <h2 className="mb-4 font-serif text-xl font-semibold text-dark">
          Fil d&apos;activite
        </h2>

        {timeline.length === 0 ? (
          <EmptyState
            icon={Inbox}
            title="Aucun evenement recent"
            description="Les evenements apparaitront ici au fil de l'activite legislative."
          />
        ) : (
          <div className="rounded-xl border border-border bg-white p-4">
            {timeline.map((item) => (
              <TimelineEvent key={item.id} item={item} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
