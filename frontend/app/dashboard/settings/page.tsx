"use client";

import { useEffect, useState } from "react";
import { useProfile } from "../ProfileContext";
import {
  Settings,
  Save,
  Plus,
  X,
  Eye,
  Radar,
  Users,
  Newspaper,
  Building,
  Globe,
  Bell,
  FileText,
} from "lucide-react";

interface WatchConfig {
  watch_keywords: string[];
  watch_keywords_exclude: string[];
  watched_politicians: string[];
  watched_ngos: string[];
  watched_regulators: string[];
  watched_media: string[];
  watched_federations: string[];
  watched_think_tanks: string[];
  watched_inspections: string[];
  eu_watch_keywords: string[];
  eu_watched_committees: string[];
  pa_strategy: string;
  pa_priorities: string[];
  notification_hours: string;
  briefing_frequency: string;
  min_signal_severity: string;
}

function TagInput({
  tags,
  onAdd,
  onRemove,
  placeholder,
}: {
  tags: string[];
  onAdd: (tag: string) => void;
  onRemove: (idx: number) => void;
  placeholder: string;
}) {
  const [input, setInput] = useState("");

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && input.trim()) {
      e.preventDefault();
      onAdd(input.trim());
      setInput("");
    }
  };

  return (
    <div>
      <div className="flex flex-wrap gap-2 mb-2">
        {tags.map((tag, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 px-3 py-1 bg-dark/5 rounded-full text-sm"
          >
            {tag}
            <button onClick={() => onRemove(i)} className="hover:text-threat">
              <X size={14} />
            </button>
          </span>
        ))}
      </div>
      <input
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        className="w-full px-3 py-2 border border-dark/10 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-warm/50"
      />
    </div>
  );
}

function Section({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: any;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-xl border border-dark/5 p-6">
      <div className="flex items-center gap-3 mb-1">
        <Icon size={20} className="text-warm" />
        <h3 className="font-semibold text-dark">{title}</h3>
      </div>
      <p className="text-sm text-dark/50 mb-4 ml-8">{description}</p>
      <div className="ml-8">{children}</div>
    </div>
  );
}

export default function SettingsPage() {
  const { activeProfile } = useProfile();
  const [config, setConfig] = useState<WatchConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!activeProfile) return;
    fetch(`/api/profiles/${activeProfile.id}`)
      .then((r) => r.json())
      .then((data) => {
        setConfig({
          watch_keywords: tryParse(data.watch_keywords, []),
          watch_keywords_exclude: tryParse(data.watch_keywords_exclude, []),
          watched_politicians: tryParse(data.watched_politicians, []),
          watched_ngos: tryParse(data.watched_ngos, []),
          watched_regulators: tryParse(data.watched_regulators, []),
          watched_media: tryParse(data.watched_media, []),
          watched_federations: tryParse(data.watched_federations, []),
          watched_think_tanks: tryParse(data.watched_think_tanks, []),
          watched_inspections: tryParse(data.watched_inspections, []),
          eu_watch_keywords: tryParse(data.eu_watch_keywords, []),
          eu_watched_committees: tryParse(data.eu_watched_committees, []),
          pa_strategy: data.pa_strategy || "",
          pa_priorities: tryParse(data.pa_priorities, []),
          notification_hours: data.notification_hours || "08:00-20:00",
          briefing_frequency: data.briefing_frequency || "daily",
          min_signal_severity: data.min_signal_severity || "medium",
        });
      });
  }, [activeProfile]);

  const handleSave = async () => {
    if (!activeProfile || !config) return;
    setSaving(true);
    try {
      await fetch(`/api/watch-config/${activeProfile.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally {
      setSaving(false);
    }
  };

  const updateTags = (field: keyof WatchConfig, tags: string[]) => {
    if (!config) return;
    setConfig({ ...config, [field]: tags });
  };

  if (!config) {
    return (
      <div className="p-8 text-dark/50">Chargement de la configuration...</div>
    );
  }

  return (
    <div className="p-8 max-w-4xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-dark flex items-center gap-3">
            <Settings size={28} />
            Configuration de la veille
          </h1>
          <p className="text-dark/50 mt-1">
            Personnalisez votre perimetre de surveillance
          </p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 bg-dark text-cream rounded-lg hover:bg-dark/90 disabled:opacity-50"
        >
          <Save size={18} />
          {saving ? "Enregistrement..." : saved ? "Enregistre !" : "Enregistrer"}
        </button>
      </div>

      <div className="space-y-6">
        {/* Mots-cles */}
        <Section
          icon={Eye}
          title="Mots-cles de veille"
          description="Termes surveilles dans tous les documents parlementaires et reglementaires"
        >
          <TagInput
            tags={config.watch_keywords}
            onAdd={(t) =>
              updateTags("watch_keywords", [...config.watch_keywords, t])
            }
            onRemove={(i) =>
              updateTags(
                "watch_keywords",
                config.watch_keywords.filter((_, idx) => idx !== i)
              )
            }
            placeholder="Ajouter un mot-cle (Entree pour valider)"
          />
          <div className="mt-4">
            <p className="text-sm font-medium text-dark/70 mb-2">
              Mots-cles exclus
            </p>
            <TagInput
              tags={config.watch_keywords_exclude}
              onAdd={(t) =>
                updateTags("watch_keywords_exclude", [
                  ...config.watch_keywords_exclude,
                  t,
                ])
              }
              onRemove={(i) =>
                updateTags(
                  "watch_keywords_exclude",
                  config.watch_keywords_exclude.filter((_, idx) => idx !== i)
                )
              }
              placeholder="Exclure un mot-cle"
            />
          </div>
        </Section>

        {/* Acteurs */}
        <Section
          icon={Users}
          title="Acteurs surveilles"
          description="Parlementaires, regulateurs et ONG suivis"
        >
          <div className="space-y-4">
            <div>
              <p className="text-sm font-medium text-dark/70 mb-2">
                Parlementaires
              </p>
              <TagInput
                tags={config.watched_politicians}
                onAdd={(t) =>
                  updateTags("watched_politicians", [
                    ...config.watched_politicians,
                    t,
                  ])
                }
                onRemove={(i) =>
                  updateTags(
                    "watched_politicians",
                    config.watched_politicians.filter((_, idx) => idx !== i)
                  )
                }
                placeholder="Nom d'un parlementaire"
              />
            </div>
            <div>
              <p className="text-sm font-medium text-dark/70 mb-2">ONG</p>
              <TagInput
                tags={config.watched_ngos}
                onAdd={(t) =>
                  updateTags("watched_ngos", [...config.watched_ngos, t])
                }
                onRemove={(i) =>
                  updateTags(
                    "watched_ngos",
                    config.watched_ngos.filter((_, idx) => idx !== i)
                  )
                }
                placeholder="Nom d'une ONG"
              />
            </div>
            <div>
              <p className="text-sm font-medium text-dark/70 mb-2">
                Regulateurs
              </p>
              <TagInput
                tags={config.watched_regulators}
                onAdd={(t) =>
                  updateTags("watched_regulators", [
                    ...config.watched_regulators,
                    t,
                  ])
                }
                onRemove={(i) =>
                  updateTags(
                    "watched_regulators",
                    config.watched_regulators.filter((_, idx) => idx !== i)
                  )
                }
                placeholder="Nom d'un regulateur (CNIL, AMF...)"
              />
            </div>
          </div>
        </Section>

        {/* Sources */}
        <Section
          icon={Newspaper}
          title="Sources suivies"
          description="Medias, federations et think tanks"
        >
          <div className="space-y-4">
            <div>
              <p className="text-sm font-medium text-dark/70 mb-2">Medias</p>
              <TagInput
                tags={config.watched_media}
                onAdd={(t) =>
                  updateTags("watched_media", [...config.watched_media, t])
                }
                onRemove={(i) =>
                  updateTags(
                    "watched_media",
                    config.watched_media.filter((_, idx) => idx !== i)
                  )
                }
                placeholder="Nom d'un media"
              />
            </div>
            <div>
              <p className="text-sm font-medium text-dark/70 mb-2">
                Federations
              </p>
              <TagInput
                tags={config.watched_federations}
                onAdd={(t) =>
                  updateTags("watched_federations", [
                    ...config.watched_federations,
                    t,
                  ])
                }
                onRemove={(i) =>
                  updateTags(
                    "watched_federations",
                    config.watched_federations.filter((_, idx) => idx !== i)
                  )
                }
                placeholder="Nom d'une federation"
              />
            </div>
            <div>
              <p className="text-sm font-medium text-dark/70 mb-2">
                Think tanks
              </p>
              <TagInput
                tags={config.watched_think_tanks}
                onAdd={(t) =>
                  updateTags("watched_think_tanks", [
                    ...config.watched_think_tanks,
                    t,
                  ])
                }
                onRemove={(i) =>
                  updateTags(
                    "watched_think_tanks",
                    config.watched_think_tanks.filter((_, idx) => idx !== i)
                  )
                }
                placeholder="Nom d'un think tank"
              />
            </div>
          </div>
        </Section>

        {/* Europe */}
        <Section
          icon={Globe}
          title="Veille europeenne"
          description="Mots-cles et comites UE surveilles"
        >
          <div className="space-y-4">
            <div>
              <p className="text-sm font-medium text-dark/70 mb-2">
                Mots-cles EU
              </p>
              <TagInput
                tags={config.eu_watch_keywords}
                onAdd={(t) =>
                  updateTags("eu_watch_keywords", [
                    ...config.eu_watch_keywords,
                    t,
                  ])
                }
                onRemove={(i) =>
                  updateTags(
                    "eu_watch_keywords",
                    config.eu_watch_keywords.filter((_, idx) => idx !== i)
                  )
                }
                placeholder="Mot-cle europeen"
              />
            </div>
            <div>
              <p className="text-sm font-medium text-dark/70 mb-2">
                Comites parlementaires EU
              </p>
              <TagInput
                tags={config.eu_watched_committees}
                onAdd={(t) =>
                  updateTags("eu_watched_committees", [
                    ...config.eu_watched_committees,
                    t,
                  ])
                }
                onRemove={(i) =>
                  updateTags(
                    "eu_watched_committees",
                    config.eu_watched_committees.filter((_, idx) => idx !== i)
                  )
                }
                placeholder="ITRE, ENVI, INTA..."
              />
            </div>
          </div>
        </Section>

        {/* Strategie PA */}
        <Section
          icon={FileText}
          title="Strategie PA"
          description="Votre strategie d'affaires publiques et vos priorites"
        >
          <div className="space-y-4">
            <div>
              <p className="text-sm font-medium text-dark/70 mb-2">
                Strategie
              </p>
              <textarea
                value={config.pa_strategy}
                onChange={(e) =>
                  setConfig({ ...config, pa_strategy: e.target.value })
                }
                rows={3}
                className="w-full px-3 py-2 border border-dark/10 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-warm/50"
                placeholder="Decrivez votre strategie PA..."
              />
            </div>
            <div>
              <p className="text-sm font-medium text-dark/70 mb-2">
                Priorites
              </p>
              <TagInput
                tags={config.pa_priorities}
                onAdd={(t) =>
                  updateTags("pa_priorities", [...config.pa_priorities, t])
                }
                onRemove={(i) =>
                  updateTags(
                    "pa_priorities",
                    config.pa_priorities.filter((_, idx) => idx !== i)
                  )
                }
                placeholder="Ajouter une priorite PA"
              />
            </div>
          </div>
        </Section>

        {/* Notifications */}
        <Section
          icon={Bell}
          title="Notifications"
          description="Parametres d'alertes et de briefings"
        >
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-sm font-medium text-dark/70 mb-2">
                Heures de notification
              </p>
              <input
                value={config.notification_hours}
                onChange={(e) =>
                  setConfig({ ...config, notification_hours: e.target.value })
                }
                className="w-full px-3 py-2 border border-dark/10 rounded-lg text-sm"
                placeholder="08:00-20:00"
              />
            </div>
            <div>
              <p className="text-sm font-medium text-dark/70 mb-2">
                Frequence briefing
              </p>
              <select
                value={config.briefing_frequency}
                onChange={(e) =>
                  setConfig({ ...config, briefing_frequency: e.target.value })
                }
                className="w-full px-3 py-2 border border-dark/10 rounded-lg text-sm"
              >
                <option value="daily">Quotidien</option>
                <option value="weekly">Hebdomadaire</option>
                <option value="realtime">Temps reel</option>
              </select>
            </div>
            <div>
              <p className="text-sm font-medium text-dark/70 mb-2">
                Severite minimum
              </p>
              <select
                value={config.min_signal_severity}
                onChange={(e) =>
                  setConfig({ ...config, min_signal_severity: e.target.value })
                }
                className="w-full px-3 py-2 border border-dark/10 rounded-lg text-sm"
              >
                <option value="low">Faible</option>
                <option value="medium">Moyen</option>
                <option value="high">Eleve</option>
                <option value="critical">Critique</option>
              </select>
            </div>
          </div>
        </Section>
      </div>
    </div>
  );
}

function tryParse(val: any, fallback: any) {
  if (!val) return fallback;
  if (Array.isArray(val)) return val;
  try {
    return JSON.parse(val);
  } catch {
    return fallback;
  }
}
