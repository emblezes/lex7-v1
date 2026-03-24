"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Loader2,
  BarChart3,
  Users,
  FileText,
  CheckCircle2,
  XCircle,
  Clock,
  TrendingUp,
  Mail,
  Phone,
  Globe,
  MapPin,
  ExternalLink,
  Shield,
  Briefcase,
  MinusCircle,
  ChevronDown,
} from "lucide-react";
import { fetchActeur, fetchTextesSuivis, fetchActeurInfluence, type Acteur, type TexteBrief, type ActeurInfluence } from "@/lib/api";
import InfluenceGauge from "@/components/InfluenceGauge";
import { useProfile } from "../../ProfileContext";

const sortColors: Record<string, string> = {
  "Adopté": "text-success",
  "Rejeté": "text-threat",
  "Retiré": "text-amber-500",
  "Tombé": "text-muted",
  "Non renseigné": "text-muted",
};

function SortIcon({ sort }: { sort: string }) {
  if (sort === "Adopté") return <CheckCircle2 className="h-3.5 w-3.5 text-success" />;
  if (sort === "Rejeté") return <XCircle className="h-3.5 w-3.5 text-threat" />;
  if (sort === "Retiré") return <MinusCircle className="h-3.5 w-3.5 text-amber-500" />;
  return <Clock className="h-3.5 w-3.5 text-muted" />;
}

function SocialIcon({ type }: { type: string }) {
  // Simple SVG icons for social media
  if (type === "twitter") return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
  );
  if (type === "facebook") return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>
  );
  if (type === "instagram") return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg>
  );
  if (type === "linkedin") return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
  );
  return null;
}

export default function ActeurDetailPage() {
  const params = useParams();
  const uid = params.uid as string;
  const { activeProfile } = useProfile();
  const [acteur, setActeur] = useState<Acteur | null>(null);
  const [briefs, setBriefs] = useState<TexteBrief[]>([]);
  const [influence, setInfluence] = useState<ActeurInfluence | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAllTextes, setShowAllTextes] = useState(false);

  useEffect(() => {
    if (!uid) return;
    setLoading(true);
    Promise.all([
      fetchActeur(uid),
      fetchActeurInfluence(uid).catch(() => null),
    ])
      .then(([a, inf]) => {
        setActeur(a);
        setInfluence(inf);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
    if (activeProfile) {
      fetchTextesSuivis(activeProfile.id)
        .then(setBriefs)
        .catch(() => setBriefs([]));
    }
  }, [uid, activeProfile]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-warm" />
      </div>
    );
  }

  if (!acteur) {
    return (
      <div className="space-y-4">
        <Link href="/dashboard/acteurs" className="inline-flex items-center gap-1 text-sm text-warm hover:text-dark">
          <ArrowLeft className="h-4 w-4" /> Retour
        </Link>
        <p className="text-muted">Acteur non trouvé.</p>
      </div>
    );
  }

  const intel = acteur.intelligence;
  const groupe = acteur.groupe_politique;
  const textes = intel?.textes_deposes ?? [];
  const textesDisplay = showAllTextes ? textes : textes.slice(0, 5);

  // Build social links
  const socialLinks = [
    acteur.twitter && { type: "twitter", url: `https://twitter.com/${acteur.twitter.replace("@", "")}`, label: acteur.twitter },
    acteur.facebook && { type: "facebook", url: acteur.facebook.startsWith("http") ? acteur.facebook : `https://facebook.com/${acteur.facebook}`, label: "Facebook" },
    acteur.instagram && { type: "instagram", url: acteur.instagram.startsWith("http") ? acteur.instagram : `https://instagram.com/${acteur.instagram}`, label: "Instagram" },
    acteur.linkedin && { type: "linkedin", url: acteur.linkedin.startsWith("http") ? acteur.linkedin : `https://linkedin.com/in/${acteur.linkedin}`, label: "LinkedIn" },
  ].filter(Boolean) as { type: string; url: string; label: string }[];

  return (
    <div className="space-y-6">
      {/* Back */}
      <Link href="/dashboard/acteurs" className="inline-flex items-center gap-1 text-sm text-warm hover:text-dark">
        <ArrowLeft className="h-4 w-4" /> Retour aux acteurs
      </Link>

      {/* Header */}
      <div className="rounded-xl bg-white p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex-1">
            <h1 className="font-serif text-3xl font-bold text-dark">
              {acteur.civilite} {acteur.prenom} {acteur.nom}
            </h1>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              {groupe && (
                <span className="rounded-full bg-warm/10 px-3 py-1 text-sm font-medium text-warm">
                  {groupe.libelle_court || groupe.libelle}
                </span>
              )}
              {acteur.profession && (
                <span className="flex items-center gap-1 text-sm text-muted">
                  <Briefcase className="h-3.5 w-3.5" />
                  {acteur.profession}
                </span>
              )}
            </div>

            {/* Contact rapide */}
            <div className="mt-4 flex flex-wrap gap-3">
              {acteur.email && (
                <a href={`mailto:${acteur.email}`} className="inline-flex items-center gap-1.5 rounded-lg bg-cream px-3 py-1.5 text-xs font-medium text-dark transition-colors hover:bg-cream-dark">
                  <Mail className="h-3.5 w-3.5" /> {acteur.email}
                </a>
              )}
              {acteur.telephone && (
                <a href={`tel:${acteur.telephone}`} className="inline-flex items-center gap-1.5 rounded-lg bg-cream px-3 py-1.5 text-xs font-medium text-dark transition-colors hover:bg-cream-dark">
                  <Phone className="h-3.5 w-3.5" /> {acteur.telephone}
                </a>
              )}
              {acteur.telephone_2 && (
                <a href={`tel:${acteur.telephone_2}`} className="inline-flex items-center gap-1.5 rounded-lg bg-cream px-3 py-1.5 text-xs font-medium text-dark transition-colors hover:bg-cream-dark">
                  <Phone className="h-3.5 w-3.5" /> {acteur.telephone_2}
                </a>
              )}
              {acteur.site_web && (
                <a href={acteur.site_web} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 rounded-lg bg-cream px-3 py-1.5 text-xs font-medium text-dark transition-colors hover:bg-cream-dark">
                  <Globe className="h-3.5 w-3.5" /> Site web
                </a>
              )}
              {acteur.hatvp_url && (
                <a href={acteur.hatvp_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 rounded-lg bg-warm/10 px-3 py-1.5 text-xs font-medium text-warm transition-colors hover:bg-warm/20">
                  <Shield className="h-3.5 w-3.5" /> Déclaration HATVP
                </a>
              )}
            </div>

            {/* Social links */}
            {socialLinks.length > 0 && (
              <div className="mt-3 flex gap-2">
                {socialLinks.map((s) => (
                  <a
                    key={s.type}
                    href={s.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-lg bg-cream px-3 py-1.5 text-xs font-medium text-dark transition-colors hover:bg-cream-dark"
                    title={s.label}
                  >
                    <SocialIcon type={s.type} />
                    {s.type === "twitter" ? s.label : s.type.charAt(0).toUpperCase() + s.type.slice(1)}
                  </a>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Influence Score */}
      {influence && (
        <div className="rounded-xl bg-white p-6">
          <h2 className="mb-4 flex items-center gap-2 font-serif text-xl font-semibold text-dark">
            <TrendingUp className="h-5 w-5 text-warm" />
            Score d&apos;influence
          </h2>
          <div className="flex items-center gap-6">
            <div className="text-center">
              <div className="text-4xl font-bold text-dark">{Math.round(influence.influence_score)}</div>
              <div className="text-xs text-muted">/ 100</div>
            </div>
            <div className="flex-1">
              <InfluenceGauge score={influence.influence_score} />
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-lg bg-cream p-3">
              <div className="text-xs font-semibold uppercase text-muted">Amendements</div>
              <div className="mt-1 text-lg font-bold text-dark">
                {Math.round(influence.breakdown.amendements.score)}
              </div>
              <div className="text-xs text-muted">{influence.breakdown.amendements.count} deposes</div>
            </div>
            <div className="rounded-lg bg-cream p-3">
              <div className="text-xs font-semibold uppercase text-muted">Adoption</div>
              <div className="mt-1 text-lg font-bold text-dark">
                {Math.round(influence.breakdown.adoption.score)}
              </div>
              <div className="text-xs text-muted">{(influence.breakdown.adoption.rate * 100).toFixed(0)}%</div>
            </div>
            <div className="rounded-lg bg-cream p-3">
              <div className="text-xs font-semibold uppercase text-muted">Commissions</div>
              <div className="mt-1 text-lg font-bold text-dark">
                {Math.round(influence.breakdown.commissions.score)}
              </div>
            </div>
            <div className="rounded-lg bg-cream p-3">
              <div className="text-xs font-semibold uppercase text-muted">Convergence</div>
              <div className="mt-1 text-lg font-bold text-dark">
                {Math.round(influence.breakdown.convergence.score)}
              </div>
              <div className="text-xs text-muted">{influence.breakdown.convergence.cosignatures} cosig.</div>
            </div>
          </div>
        </div>
      )}

      {/* Intelligence section */}
      {intel ? (
        <>
          {/* Stats globales — 6 cards */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
            <div className="rounded-xl bg-white p-4">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted">Amendements</div>
              <p className="mt-1 text-2xl font-bold text-dark">{intel.stats.nb_amendements}</p>
            </div>
            <div className="rounded-xl bg-white p-4">
              <div className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-success">
                <CheckCircle2 className="h-3.5 w-3.5" /> Adoptés
              </div>
              <p className="mt-1 text-2xl font-bold text-success">{intel.stats.nb_adoptes}</p>
            </div>
            <div className="rounded-xl bg-white p-4">
              <div className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-threat">
                <XCircle className="h-3.5 w-3.5" /> Rejetés
              </div>
              <p className="mt-1 text-2xl font-bold text-threat">{intel.stats.nb_rejetes}</p>
            </div>
            <div className="rounded-xl bg-white p-4">
              <div className="text-xs font-semibold uppercase tracking-wider text-amber-600">Retirés</div>
              <p className="mt-1 text-2xl font-bold text-amber-600">{intel.stats.nb_retires ?? 0}</p>
            </div>
            <div className="rounded-xl bg-white p-4">
              <div className="text-xs font-semibold uppercase tracking-wider text-muted">Tombés</div>
              <p className="mt-1 text-2xl font-bold text-muted">{intel.stats.nb_tombes ?? 0}</p>
            </div>
            <div className="rounded-xl bg-dark p-4">
              <div className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wider text-white/70">
                <TrendingUp className="h-3.5 w-3.5" /> Taux adoption
              </div>
              <p className="mt-1 text-2xl font-bold text-white">
                {(intel.stats.taux_adoption * 100).toFixed(1)}%
              </p>
            </div>
          </div>

          {/* Adoption par theme */}
          {Object.keys(intel.adoption_par_theme).length > 0 && (
            <div className="rounded-xl bg-white p-6">
              <h2 className="mb-4 flex items-center gap-2 font-serif text-xl font-semibold text-dark">
                <BarChart3 className="h-5 w-5 text-warm" />
                Adoption par thème
              </h2>
              <div className="space-y-3">
                {Object.entries(intel.adoption_par_theme).map(([theme, data]) => {
                  const pct = data.taux_adoption * 100;
                  return (
                    <div key={theme}>
                      <div className="mb-1 flex items-center justify-between">
                        <span className="text-sm font-medium capitalize text-dark">
                          {theme.replace("/", " / ")}
                        </span>
                        <span className="text-sm text-muted">
                          {data.adoptes}/{data.total} ({pct.toFixed(0)}%)
                        </span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-cream">
                        <div
                          className="h-full rounded-full bg-warm transition-all"
                          style={{ width: `${Math.min(pct, 100)}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Textes deposes */}
          {textes.length > 0 && (
            <div className="rounded-xl bg-white p-6">
              <h2 className="mb-4 flex items-center gap-2 font-serif text-xl font-semibold text-dark">
                <FileText className="h-5 w-5 text-warm" />
                Textes déposés
                <span className="ml-1 rounded-full bg-cream px-2 py-0.5 text-xs font-bold text-warm">
                  {textes.length}
                </span>
              </h2>
              <div className="space-y-2">
                {textesDisplay.map((t) => (
                  <Link
                    key={t.uid}
                    href={`/dashboard/dossiers/${t.uid}`}
                    className="flex items-start gap-3 rounded-lg p-3 transition-colors hover:bg-cream"
                  >
                    <FileText className="mt-0.5 h-4 w-4 flex-shrink-0 text-warm" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-dark line-clamp-2">
                        {t.titre}
                      </p>
                      <div className="mt-1 flex flex-wrap items-center gap-2">
                        {t.denomination && (
                          <span className="rounded bg-cream px-1.5 py-0.5 text-xs text-muted">
                            {t.denomination}
                          </span>
                        )}
                        {t.date_depot && (
                          <span className="text-xs text-muted">
                            {new Date(t.date_depot).toLocaleDateString("fr-FR")}
                          </span>
                        )}
                        {t.themes.slice(0, 2).map((theme) => (
                          <span key={theme} className="rounded bg-warm/10 px-1.5 py-0.5 text-xs text-warm capitalize">
                            {theme}
                          </span>
                        ))}
                      </div>
                    </div>
                    <ExternalLink className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-muted" />
                  </Link>
                ))}
              </div>
              {textes.length > 5 && (
                <button
                  onClick={() => setShowAllTextes(!showAllTextes)}
                  className="mt-3 flex w-full items-center justify-center gap-1 rounded-lg py-2 text-sm font-medium text-warm transition-colors hover:bg-cream"
                >
                  {showAllTextes ? "Voir moins" : `Voir les ${textes.length} textes`}
                  <ChevronDown className={`h-4 w-4 transition-transform ${showAllTextes ? "rotate-180" : ""}`} />
                </button>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Cosignataires frequents */}
            {intel.cosignataires_frequents.length > 0 && (
              <div className="rounded-xl bg-white p-6">
                <h2 className="mb-4 flex items-center gap-2 font-serif text-xl font-semibold text-dark">
                  <Users className="h-5 w-5 text-warm" />
                  Cosignataires fréquents
                </h2>
                <div className="space-y-2">
                  {intel.cosignataires_frequents.map((cosig) => (
                    <Link
                      key={cosig.uid}
                      href={`/dashboard/acteurs/${cosig.uid}`}
                      className="flex items-center justify-between rounded-lg p-3 transition-colors hover:bg-cream"
                    >
                      <div>
                        <p className="text-sm font-medium text-dark">
                          {cosig.nom}
                        </p>
                        <p className="text-xs text-muted">{cosig.groupe}</p>
                      </div>
                      <span className="rounded-full bg-cream px-2.5 py-0.5 text-xs font-bold text-warm">
                        {cosig.nb_cosignatures}
                      </span>
                    </Link>
                  ))}
                </div>
              </div>
            )}

            {/* Activite recente */}
            {intel.activite_recente_30j.length > 0 && (
              <div className="rounded-xl bg-white p-6">
                <h2 className="mb-4 flex items-center gap-2 font-serif text-xl font-semibold text-dark">
                  <Clock className="h-5 w-5 text-warm" />
                  Activité récente (30j)
                </h2>
                <div className="space-y-2">
                  {intel.activite_recente_30j.map((amdt) => (
                    <div
                      key={amdt.uid}
                      className="rounded-lg border border-border p-3"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <SortIcon sort={amdt.sort} />
                          <span className="text-sm font-medium text-dark">
                            Amdt. n°{amdt.numero}
                          </span>
                          <span className={`text-xs font-medium ${sortColors[amdt.sort] || "text-muted"}`}>
                            {amdt.sort}
                          </span>
                        </div>
                        {amdt.date_depot && (
                          <span className="text-xs text-muted">
                            {new Date(amdt.date_depot).toLocaleDateString("fr-FR")}
                          </span>
                        )}
                      </div>
                      {amdt.texte_titre && (
                        <Link
                          href={`/dashboard/dossiers/${amdt.texte_ref}`}
                          className="mt-1 block text-xs text-warm hover:underline line-clamp-1"
                        >
                          {amdt.texte_titre}
                        </Link>
                      )}
                      {amdt.article_vise && (
                        <span className="mt-0.5 block text-xs text-muted">
                          {amdt.article_vise}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </>
      ) : (
        <div className="rounded-xl bg-white p-8 text-center">
          <BarChart3 className="mx-auto h-8 w-8 text-warm/30" />
          <p className="mt-3 text-sm text-muted">
            Pas de données d&apos;intelligence disponibles pour cet acteur.
          </p>
        </div>
      )}

      {/* Dossiers en commun */}
      {(() => {
        const dossiersCommun = briefs.filter((b) =>
          b.key_contacts?.some((c) => c.uid === uid),
        );
        if (dossiersCommun.length === 0) return null;
        return (
          <div className="rounded-xl bg-white p-6">
            <h2 className="mb-4 flex items-center gap-2 font-serif text-xl font-semibold text-dark">
              <FileText className="h-5 w-5 text-warm" />
              Dossiers en commun
              <span className="ml-1 rounded-full bg-cream px-2 py-0.5 text-xs font-bold text-warm">
                {dossiersCommun.length}
              </span>
            </h2>
            <div className="space-y-2">
              {dossiersCommun.map((b) => (
                <Link
                  key={b.id}
                  href={`/dashboard/dossiers/${b.texte_uid}`}
                  className="flex items-center gap-3 rounded-lg p-3 transition-colors hover:bg-cream"
                >
                  <FileText className="h-4 w-4 flex-shrink-0 text-warm" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-dark line-clamp-1">
                      {b.texte?.titre || b.texte_uid}
                    </p>
                    <p className="mt-0.5 text-xs text-muted">
                      Impact {b.impact_level} — {b.is_threat ? "Menace" : "Opportunite"}
                    </p>
                  </div>
                  <ExternalLink className="h-3.5 w-3.5 flex-shrink-0 text-muted" />
                </Link>
              ))}
            </div>
          </div>
        );
      })()}

      {/* Adresses + Collaborateurs side by side */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Adresses */}
        {(acteur.adresse_an || acteur.adresse_circo) && (
          <div className="rounded-xl bg-white p-6">
            <h2 className="mb-4 flex items-center gap-2 font-serif text-xl font-semibold text-dark">
              <MapPin className="h-5 w-5 text-warm" />
              Adresses
            </h2>
            <div className="space-y-4">
              {acteur.adresse_an && (
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">
                    Assemblée nationale
                  </p>
                  <p className="text-sm text-dark whitespace-pre-line">{acteur.adresse_an}</p>
                </div>
              )}
              {acteur.adresse_circo && (
                <div>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">
                    Circonscription
                  </p>
                  <p className="text-sm text-dark whitespace-pre-line">{acteur.adresse_circo}</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Collaborateurs */}
        {acteur.collaborateurs.length > 0 && (
          <div className="rounded-xl bg-white p-6">
            <h2 className="mb-4 flex items-center gap-2 font-serif text-xl font-semibold text-dark">
              <Users className="h-5 w-5 text-warm" />
              Collaborateurs
            </h2>
            <div className="flex flex-wrap gap-2">
              {acteur.collaborateurs.map((c, i) => (
                <span
                  key={i}
                  className="rounded-full bg-cream px-3 py-1 text-sm text-dark"
                >
                  {c.civilite} {c.nom}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
