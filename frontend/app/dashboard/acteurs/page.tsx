"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import {
  Search,
  Mail,
  Phone,
  User,
  Loader2,
  ArrowRight,
  FolderOpen,
  Filter,
  Building2,
  TrendingUp,
  BarChart3,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import {
  fetchActeurs,
  fetchTextesSuivis,
  fetchGroupes,
  type ActeurListItem,
  type ActeurListResponse,
  type TexteBrief,
  type GroupeInfo,
} from "@/lib/api";
import { useProfile } from "../ProfileContext";

export default function ActeursPage() {
  const { activeProfile } = useProfile();
  const [response, setResponse] = useState<ActeurListResponse | null>(null);
  const [briefs, setBriefs] = useState<TexteBrief[]>([]);
  const [groupes, setGroupes] = useState<GroupeInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchTimeout, setSearchTimeout] = useState<NodeJS.Timeout | null>(null);
  const [filterLinked, setFilterLinked] = useState(false);
  const [filterGroupeRef, setFilterGroupeRef] = useState<string>("");
  const [page, setPage] = useState(0);
  const pageSize = 30;

  // Charger les groupes au mount
  useEffect(() => {
    fetchGroupes().then(setGroupes).catch(() => setGroupes([]));
  }, []);

  const loadActeurs = useCallback(
    (search?: string, groupeRef?: string, offset = 0) => {
      setLoading(true);
      const params: Record<string, unknown> = {
        limit: pageSize,
        offset,
        with_stats: true,
      };
      if (search) params.search = search;
      if (groupeRef) params.groupe_ref = groupeRef;
      fetchActeurs(params)
        .then((data) => setResponse(data))
        .catch(console.error)
        .finally(() => setLoading(false));
    },
    []
  );

  useEffect(() => {
    loadActeurs(
      searchQuery || undefined,
      filterGroupeRef || undefined,
      page * pageSize
    );
    if (activeProfile) {
      fetchTextesSuivis(activeProfile.id)
        .then(setBriefs)
        .catch(() => setBriefs([]));
    }
  }, [loadActeurs, activeProfile, filterGroupeRef, page, searchQuery]);

  const handleSearch = (value: string) => {
    setSearchQuery(value);
    setPage(0);
    if (searchTimeout) clearTimeout(searchTimeout);
    const timeout = setTimeout(() => {
      loadActeurs(value, filterGroupeRef || undefined, 0);
    }, 400);
    setSearchTimeout(timeout);
  };

  // Extract all key_contacts UIDs from briefs
  const linkedUids = useMemo(() => {
    const uids = new Map<string, number>();
    for (const b of briefs) {
      for (const c of b.key_contacts || []) {
        uids.set(c.uid, (uids.get(c.uid) || 0) + 1);
      }
    }
    return uids;
  }, [briefs]);

  const acteurs = response?.items ?? [];
  const total = response?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  const displayActeurs = useMemo(() => {
    if (!filterLinked) return acteurs;
    return acteurs.filter((a) => linkedUids.has(a.uid));
  }, [acteurs, filterLinked, linkedUids]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-serif text-3xl font-bold text-dark">Acteurs</h1>
        <p className="mt-1 text-sm text-muted">
          {total} parlementaires en base
          {displayActeurs.length !== total &&
            ` — ${displayActeurs.length} affiches`}
        </p>
      </div>

      {/* Search + Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Rechercher un acteur..."
            className="w-full rounded-lg border border-border bg-white py-2.5 pl-10 pr-4 text-sm text-dark placeholder:text-muted/50 focus:border-warm focus:outline-none focus:ring-1 focus:ring-warm"
          />
        </div>
        <select
          value={filterGroupeRef}
          onChange={(e) => {
            setFilterGroupeRef(e.target.value);
            setPage(0);
          }}
          className="rounded-lg border border-border bg-white px-3 py-2.5 text-sm text-dark focus:border-warm focus:outline-none"
        >
          <option value="">Tous les groupes</option>
          {groupes.map((g) => (
            <option key={g.uid} value={g.uid}>
              {g.libelle_court || g.libelle} ({g.nb_deputes})
            </option>
          ))}
        </select>
        {briefs.length > 0 && (
          <button
            onClick={() => setFilterLinked(!filterLinked)}
            className={`flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium transition-colors ${
              filterLinked
                ? "bg-dark text-white"
                : "bg-white text-muted border border-border hover:bg-cream"
            }`}
          >
            <FolderOpen className="h-4 w-4" />
            Lies a mes dossiers
          </button>
        )}
      </div>

      {/* Grid */}
      {loading ? (
        <div className="flex h-32 items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-warm" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {displayActeurs.length === 0 && (
            <p className="text-sm text-muted">Aucun acteur trouve.</p>
          )}
          {displayActeurs.map((acteur) => {
            const nbDossiers = linkedUids.get(acteur.uid) || 0;
            const stats = acteur.stats;
            return (
              <Link
                key={acteur.uid}
                href={`/dashboard/acteurs/${acteur.uid}`}
                className={`block rounded-xl bg-white p-5 transition-shadow hover:shadow-md ${
                  nbDossiers > 0 ? "ring-2 ring-warm/20" : ""
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full bg-cream-dark">
                    <User className="h-6 w-6 text-muted" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <h3 className="font-serif text-base font-semibold text-dark">
                        {acteur.civilite} {acteur.prenom} {acteur.nom}
                      </h3>
                      <ArrowRight className="h-4 w-4 flex-shrink-0 text-warm" />
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-2">
                      {acteur.groupe_politique && (
                        <span className="rounded-full bg-warm/10 px-2 py-0.5 text-xs font-medium text-warm">
                          {acteur.groupe_politique.libelle_court ||
                            acteur.groupe_politique.libelle}
                        </span>
                      )}
                      {acteur.profession && (
                        <span className="text-xs text-muted truncate">
                          {acteur.profession}
                        </span>
                      )}
                    </div>

                    {/* Stats amendements */}
                    {stats && stats.nb_amendements > 0 && (
                      <div className="mt-2 flex items-center gap-3 text-xs">
                        <span className="flex items-center gap-1 text-muted">
                          <BarChart3 className="h-3 w-3" />
                          {stats.nb_amendements} amdts
                        </span>
                        <span className="flex items-center gap-1 text-success">
                          <CheckCircle2 className="h-3 w-3" />
                          {stats.nb_adoptes} adoptes
                        </span>
                        {stats.taux_adoption > 0 && (
                          <span className="flex items-center gap-1 font-medium text-dark">
                            <TrendingUp className="h-3 w-3" />
                            {(stats.taux_adoption * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>
                    )}

                    {nbDossiers > 0 && (
                      <p className="mt-1 text-xs font-medium text-warm">
                        Apparait dans {nbDossiers} dossier
                        {nbDossiers > 1 ? "s" : ""}
                      </p>
                    )}
                    <div className="mt-2 space-y-1">
                      {acteur.email && (
                        <div className="flex items-center gap-2 text-xs text-muted">
                          <Mail className="h-3.5 w-3.5 flex-shrink-0" />
                          <span className="truncate">{acteur.email}</span>
                        </div>
                      )}
                      {acteur.telephone && (
                        <div className="flex items-center gap-2 text-xs text-muted">
                          <Phone className="h-3.5 w-3.5 flex-shrink-0" />
                          <span>{acteur.telephone}</span>
                        </div>
                      )}
                    </div>
                    {nbDossiers > 0 && (
                      <div className="mt-3">
                        <span
                          onClick={(e) => e.stopPropagation()}
                          className="inline-block"
                        >
                          <Link
                            href={`/dashboard/chat?prompt=Redige un email a ${acteur.prenom} ${acteur.nom}&agent=redacteur`}
                            className="inline-flex items-center gap-1 rounded bg-warm/10 px-2 py-1 text-xs font-medium text-warm hover:bg-warm/20"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <Mail className="h-3 w-3" />
                            Mail suggere
                          </Link>
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </Link>
            );
          })}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-4">
          <button
            onClick={() => setPage(Math.max(0, page - 1))}
            disabled={page === 0}
            className="inline-flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium text-dark transition-colors hover:bg-cream disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronLeft className="h-4 w-4" />
            Precedent
          </button>
          <span className="text-sm text-muted">
            Page {page + 1} / {totalPages}
          </span>
          <button
            onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
            disabled={page >= totalPages - 1}
            className="inline-flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-medium text-dark transition-colors hover:bg-cream disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Suivant
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
