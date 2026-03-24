"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import {
  CheckSquare,
  Play,
  Clock,
  CheckCircle2,
  Loader2,
  FileText,
  Mail,
  PenTool,
  Eye,
  Download,
  Zap,
  Inbox,
} from "lucide-react";
import { useProfile } from "../ProfileContext";
import {
  fetchActions,
  executeAction,
  fetchProfileAlertes,
  generateBriefing,
  type ActionTask,
  type ImpactAlert,
} from "@/lib/api";
import EmptyState from "@/components/EmptyState";
import { timeAgo } from "@/components/utils";

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

const statusConfig: Record<string, { label: string; color: string; icon: typeof Clock }> = {
  pending: { label: "A faire", color: "bg-amber-100 text-amber-800", icon: Clock },
  in_progress: { label: "En cours", color: "bg-blue-100 text-blue-800", icon: Loader2 },
  completed: { label: "Termine", color: "bg-emerald-100 text-emerald-800", icon: CheckCircle2 },
};

export default function ActionsPage() {
  const { activeProfile } = useProfile();
  const [actions, setActions] = useState<ActionTask[]>([]);
  const [alerts, setAlerts] = useState<ImpactAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState<number | null>(null);
  const [generating, setGenerating] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!activeProfile) return;
    setLoading(true);
    Promise.all([
      fetchActions({ profile_id: activeProfile.id }).catch(() => []),
      fetchProfileAlertes(activeProfile.id, { limit: 20 }).catch(() => []),
    ])
      .then(([actionsData, alertsData]) => {
        setActions(actionsData as ActionTask[]);
        setAlerts(alertsData);
      })
      .finally(() => setLoading(false));
  }, [activeProfile]);

  const pending = useMemo(() => actions.filter((a) => a.status === "pending"), [actions]);
  const inProgress = useMemo(() => actions.filter((a) => a.status === "in_progress"), [actions]);
  const completed = useMemo(() => actions.filter((a) => a.status === "completed"), [actions]);

  // Fallback: derive suggested actions from critical/high alerts
  const suggestedActions = useMemo(() => {
    if (actions.length > 0) return [];
    const criticalAlerts = alerts.filter(
      (a) => a.impact_level === "critical" || a.impact_level === "high",
    );
    const suggestions: { label: string; type: string; alertId: number; rationale: string }[] = [];
    for (const alert of criticalAlerts.slice(0, 5)) {
      for (const action of alert.actions || []) {
        suggestions.push({
          label: action.label,
          type: action.type,
          alertId: alert.id,
          rationale: alert.impact_summary?.split(".")[0] || "",
        });
      }
    }
    return suggestions.slice(0, 6);
  }, [actions, alerts]);

  const handleExecute = async (taskId: number) => {
    setExecuting(taskId);
    try {
      const updated = await executeAction(taskId);
      setActions((prev) => prev.map((a) => (a.id === taskId ? updated : a)));
    } catch {
      /* ignore */
    }
    setExecuting(null);
  };

  const handleGenerateBriefing = async () => {
    setGenerating(true);
    try {
      await generateBriefing();
    } catch {
      /* ignore */
    }
    setGenerating(false);
  };

  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (!activeProfile) {
    return (
      <div className="flex h-96 items-center justify-center text-muted">
        Selectionnez un client pour voir les actions.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-warm" />
      </div>
    );
  }

  const hasActions = actions.length > 0;

  function renderActionCard(action: ActionTask) {
    const Icon = typeIcons[action.action_type] || FileText;
    const cfg = statusConfig[action.status] || statusConfig.pending;
    const StatusIcon = cfg.icon;
    const isExpanded = expandedIds.has(action.id);

    return (
      <div
        key={action.id}
        className="rounded-xl border border-border bg-white p-5"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 flex-1">
            <Icon className="mt-0.5 h-5 w-5 flex-shrink-0 text-muted" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-dark">{action.label}</p>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium ${cfg.color}`}>
                  <StatusIcon className="h-3 w-3" />
                  {cfg.label}
                </span>
                {action.action_type && (
                  <span className="text-muted">
                    {typeLabels[action.action_type] || action.action_type}
                  </span>
                )}
                {action.due_date && (
                  <span className="text-muted">
                    Echeance : {new Date(action.due_date).toLocaleDateString("fr-FR")}
                  </span>
                )}
                {action.created_at && (
                  <span className="text-muted">{timeAgo(action.created_at)}</span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {action.status === "pending" && (
              <button
                onClick={() => handleExecute(action.id)}
                disabled={executing === action.id}
                className="flex items-center gap-1 rounded-lg bg-warm px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-warm/90 disabled:opacity-50"
              >
                {executing === action.id ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Play className="h-3 w-3" />
                )}
                Executer
              </button>
            )}
            {action.status === "completed" && action.result_content && (
              <button
                onClick={() => toggleExpand(action.id)}
                className="flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-cream"
              >
                <Download className="h-3 w-3" />
                {isExpanded ? "Masquer" : "Voir"}
              </button>
            )}
          </div>
        </div>
        {isExpanded && action.result_content && (
          <div className="mt-3 rounded-lg bg-cream p-4">
            <div className="prose prose-sm max-w-none text-dark">
              <pre className="whitespace-pre-wrap text-sm">{action.result_content}</pre>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-serif text-2xl font-bold text-dark">Actions</h1>
        <p className="mt-1 text-sm text-muted">
          {activeProfile.name} — {actions.length} action{actions.length !== 1 ? "s" : ""}
        </p>
      </div>

      {hasActions ? (
        <>
          {/* A faire */}
          {pending.length > 0 && (
            <div>
              <h2 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-amber-700">
                <Clock className="h-4 w-4" />
                A faire ({pending.length})
              </h2>
              <div className="space-y-3">
                {pending.map(renderActionCard)}
              </div>
            </div>
          )}

          {/* En cours */}
          {inProgress.length > 0 && (
            <div>
              <h2 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-blue-700">
                <Loader2 className="h-4 w-4" />
                En cours ({inProgress.length})
              </h2>
              <div className="space-y-3">
                {inProgress.map(renderActionCard)}
              </div>
            </div>
          )}

          {/* Termine */}
          {completed.length > 0 && (
            <div>
              <h2 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-emerald-700">
                <CheckCircle2 className="h-4 w-4" />
                Termine ({completed.length})
              </h2>
              <div className="space-y-3">
                {completed.map(renderActionCard)}
              </div>
            </div>
          )}
        </>
      ) : (
        <div>
          {suggestedActions.length > 0 ? (
            <div>
              <div className="mb-4 flex items-center justify-between">
                <h2 className="font-serif text-lg font-semibold text-dark">
                  Actions suggerees par vos agents
                </h2>
                <button
                  onClick={handleGenerateBriefing}
                  disabled={generating}
                  className="flex items-center gap-2 rounded-lg bg-warm px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-warm/90 disabled:opacity-50"
                >
                  {generating ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Zap className="h-4 w-4" />
                  )}
                  Generer un briefing
                </button>
              </div>
              <div className="space-y-3">
                {suggestedActions.map((sa, i) => {
                  const Icon = typeIcons[sa.type] || FileText;
                  return (
                    <Link
                      key={i}
                      href={`/dashboard/alertes/${sa.alertId}`}
                      className="group block rounded-xl border border-border bg-white p-5 transition-all hover:shadow-md"
                    >
                      <div className="flex items-start gap-3">
                        <Icon className="mt-0.5 h-5 w-5 flex-shrink-0 text-muted" />
                        <div>
                          <p className="text-sm font-medium text-dark group-hover:text-warm">
                            {sa.label}
                          </p>
                          {sa.rationale && (
                            <p className="mt-1 text-xs text-muted">
                              {sa.rationale}
                            </p>
                          )}
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            </div>
          ) : (
            <EmptyState
              icon={Inbox}
              title="Aucune action pour le moment"
              description="Les actions seront generees automatiquement quand vos agents detectent des textes vous concernant."
            />
          )}
        </div>
      )}
    </div>
  );
}
