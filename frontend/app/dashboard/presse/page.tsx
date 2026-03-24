"use client";

import { useEffect, useState } from "react";
import { useProfile } from "../ProfileContext";
import {
  Newspaper,
  AlertCircle,
  TrendingDown,
  TrendingUp,
  Minus,
  ExternalLink,
  Clock,
  Shield,
  MessageCircle,
} from "lucide-react";

interface PressArticle {
  id: number;
  title: string;
  source_name: string;
  author: string | null;
  publication_date: string | null;
  sentiment: string | null;
  requires_response: boolean;
  response_urgency: string | null;
  response_status: string;
  url: string;
}

const SENTIMENT_CONFIG: Record<
  string,
  { icon: typeof TrendingUp; color: string; label: string }
> = {
  positive: {
    icon: TrendingUp,
    color: "text-green-600",
    label: "Positif",
  },
  negative: {
    icon: TrendingDown,
    color: "text-red-600",
    label: "Négatif",
  },
  neutral: { icon: Minus, color: "text-gray-500", label: "Neutre" },
  mixed: {
    icon: AlertCircle,
    color: "text-amber-600",
    label: "Mixte",
  },
};

const URGENCY_COLORS: Record<string, string> = {
  critical: "bg-red-100 text-red-700 border-red-200",
  high: "bg-orange-100 text-orange-700 border-orange-200",
  medium: "bg-amber-100 text-amber-700 border-amber-200",
  low: "bg-blue-100 text-blue-700 border-blue-200",
};

export default function PressePage() {
  const { activeProfile } = useProfile();
  const [tab, setTab] = useState<"review" | "mentions" | "riposte">("review");
  const [articles, setArticles] = useState<PressArticle[]>([]);
  const [mentions, setMentions] = useState<any>(null);
  const [riposteQueue, setRiposteQueue] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const profileParam = activeProfile?.id
      ? `&profile_id=${activeProfile.id}`
      : "";

    Promise.all([
      fetch(`/api/presse/articles?limit=30${profileParam}`).then((r) =>
        r.json()
      ),
      activeProfile?.id
        ? fetch(
            `/api/presse/mentions?profile_id=${activeProfile.id}&days=7`
          ).then((r) => r.json())
        : Promise.resolve(null),
      fetch(
        `/api/presse/riposte-queue${activeProfile?.id ? `?profile_id=${activeProfile.id}` : ""}`
      ).then((r) => r.json()),
      fetch(
        `/api/presse/stats${activeProfile?.id ? `?profile_id=${activeProfile.id}` : ""}`
      ).then((r) => r.json()),
    ])
      .then(([articlesData, mentionsData, riposteData, statsData]) => {
        setArticles(articlesData.items || []);
        setMentions(mentionsData);
        setRiposteQueue(riposteData);
        setStats(statsData);
      })
      .finally(() => setLoading(false));
  }, [activeProfile]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-muted">
        Chargement de la veille presse...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-serif text-3xl font-bold text-dark">Presse</h1>
        <p className="mt-1 text-sm text-muted">
          Monitoring médiatique, mentions client et file de riposte
        </p>
      </div>

      {/* Stats rapides */}
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          <div className="rounded-xl border border-border bg-white p-4">
            <div className="text-2xl font-bold text-dark">{stats.total}</div>
            <div className="text-xs text-muted">Articles suivis</div>
          </div>
          <div className="rounded-xl border border-border bg-white p-4">
            <div className="text-2xl font-bold text-green-600">
              {stats.by_sentiment?.positive || 0}
            </div>
            <div className="text-xs text-muted">Positifs</div>
          </div>
          <div className="rounded-xl border border-border bg-white p-4">
            <div className="text-2xl font-bold text-red-600">
              {stats.by_sentiment?.negative || 0}
            </div>
            <div className="text-xs text-muted">Négatifs</div>
          </div>
          <div className="rounded-xl border border-border bg-white p-4">
            <div className="text-2xl font-bold text-amber-600">
              {riposteQueue?.total || 0}
            </div>
            <div className="text-xs text-muted">En attente de riposte</div>
          </div>
        </div>
      )}

      {/* Onglets */}
      <div className="flex gap-1 rounded-lg bg-white p-1">
        {[
          { key: "review" as const, label: "Revue de presse", icon: Newspaper },
          {
            key: "mentions" as const,
            label: "Mentions",
            icon: MessageCircle,
          },
          { key: "riposte" as const, label: "File riposte", icon: Shield },
        ].map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                tab === t.key
                  ? "bg-dark text-white"
                  : "text-muted hover:bg-cream"
              }`}
            >
              <Icon className="h-4 w-4" />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* Contenu des onglets */}
      {tab === "review" && (
        <div className="space-y-3">
          {articles.length === 0 ? (
            <div className="rounded-xl border border-border bg-white p-8 text-center text-muted">
              Aucun article de presse pour le moment. Les collecteurs presse
              sont actifs.
            </div>
          ) : (
            articles.map((article) => {
              const sentimentConfig =
                SENTIMENT_CONFIG[article.sentiment || "neutral"];
              const SentimentIcon = sentimentConfig?.icon || Minus;

              return (
                <div
                  key={article.id}
                  className="rounded-xl border border-border bg-white p-4 transition-shadow hover:shadow-sm"
                >
                  <div className="flex items-start gap-3">
                    <SentimentIcon
                      className={`mt-0.5 h-5 w-5 flex-shrink-0 ${sentimentConfig?.color || "text-gray-500"}`}
                    />
                    <div className="flex-1">
                      <h3 className="font-medium text-dark">
                        {article.title}
                      </h3>
                      <div className="mt-1 flex items-center gap-3 text-xs text-muted">
                        <span className="font-medium">
                          {article.source_name}
                        </span>
                        {article.author && <span>par {article.author}</span>}
                        {article.publication_date && (
                          <>
                            <Clock className="h-3 w-3" />
                            <span>
                              {new Date(
                                article.publication_date
                              ).toLocaleDateString("fr-FR")}
                            </span>
                          </>
                        )}
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs ${sentimentConfig?.color || ""}`}
                        >
                          {sentimentConfig?.label || "N/A"}
                        </span>
                      </div>
                      {article.requires_response && (
                        <div
                          className={`mt-2 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${URGENCY_COLORS[article.response_urgency || "medium"]}`}
                        >
                          <AlertCircle className="h-3 w-3" />
                          Réponse requise ({article.response_urgency})
                        </div>
                      )}
                    </div>
                    {article.url && (
                      <a
                        href={article.url}
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
      )}

      {tab === "mentions" && mentions && (
        <div className="space-y-4">
          <div className="rounded-xl border border-border bg-white p-5">
            <h3 className="font-medium text-dark">
              Mentions de {activeProfile?.name || "votre entreprise"} (7
              derniers jours)
            </h3>
            <div className="mt-3 grid grid-cols-4 gap-3">
              <div className="text-center">
                <div className="text-xl font-bold text-dark">
                  {mentions.total_mentions}
                </div>
                <div className="text-xs text-muted">Total</div>
              </div>
              <div className="text-center">
                <div className="text-xl font-bold text-green-600">
                  {mentions.by_sentiment?.positive || 0}
                </div>
                <div className="text-xs text-muted">Positifs</div>
              </div>
              <div className="text-center">
                <div className="text-xl font-bold text-red-600">
                  {mentions.by_sentiment?.negative || 0}
                </div>
                <div className="text-xs text-muted">Négatifs</div>
              </div>
              <div className="text-center">
                <div className="text-xl font-bold text-gray-600">
                  {mentions.by_sentiment?.neutral || 0}
                </div>
                <div className="text-xs text-muted">Neutres</div>
              </div>
            </div>
          </div>
          {mentions.all_mentions?.map((a: PressArticle) => (
            <div
              key={a.id}
              className="rounded-lg border border-border bg-white p-3 text-sm"
            >
              <div className="font-medium text-dark">{a.title}</div>
              <div className="mt-1 text-xs text-muted">
                {a.source_name} — {a.sentiment}
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "riposte" && riposteQueue && (
        <div className="space-y-4">
          {riposteQueue.total === 0 ? (
            <div className="rounded-xl border border-green-200 bg-green-50 p-6 text-center">
              <Shield className="mx-auto h-8 w-8 text-green-600" />
              <p className="mt-2 font-medium text-green-700">
                Aucune riposte en attente
              </p>
              <p className="text-sm text-green-600">
                Tous les articles sont traités.
              </p>
            </div>
          ) : (
            <>
              {riposteQueue.critical?.length > 0 && (
                <div>
                  <h3 className="mb-2 text-sm font-bold uppercase text-red-600">
                    Critique
                  </h3>
                  {riposteQueue.critical.map((a: PressArticle) => (
                    <RiposteCard key={a.id} article={a} />
                  ))}
                </div>
              )}
              {riposteQueue.high?.length > 0 && (
                <div>
                  <h3 className="mb-2 text-sm font-bold uppercase text-orange-600">
                    Élevé
                  </h3>
                  {riposteQueue.high.map((a: PressArticle) => (
                    <RiposteCard key={a.id} article={a} />
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function RiposteCard({ article }: { article: PressArticle }) {
  return (
    <div
      className={`mb-2 rounded-xl border p-4 ${URGENCY_COLORS[article.response_urgency || "medium"]}`}
    >
      <div className="flex items-start justify-between">
        <div>
          <h4 className="font-medium">{article.title}</h4>
          <div className="mt-1 text-xs">
            {article.source_name}
            {article.author && ` — ${article.author}`}
          </div>
        </div>
        <span className="rounded-full bg-white/50 px-2 py-0.5 text-xs font-medium">
          {article.response_status === "none" ? "En attente" : "Brouillon"}
        </span>
      </div>
    </div>
  );
}
