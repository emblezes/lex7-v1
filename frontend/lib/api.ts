const API_BASE = "/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface OrganeInfo {
  uid: string;
  libelle: string;
  libelle_court: string;
  type?: string;
}

export interface AuteurInfo {
  uid: string;
  civilite: string;
  prenom: string;
  nom: string;
  groupe_politique?: OrganeInfo | null;
}

export interface Texte {
  uid: string;
  legislature: number;
  denomination: string;
  titre: string;
  titre_court: string;
  type_code: string;
  type_libelle: string;
  date_depot: string | null;
  date_publication: string | null;
  source: string;
  source_label?: string;
  themes: string[];
  resume_ia: string | null;
  score_impact: string | null;
  url_source: string | null;
  dossier_ref: string | null;
  organe_ref: string | null;
  auteur_texte: string | null;
  created_at: string | null;
  amendements_count?: number;
  amendements?: AmendementDetail[];
  auteurs?: AuteurInfo[];
  commission?: OrganeInfo | null;
  amendements_stats?: Record<string, number>;
}

export interface AmendementDetail {
  uid: string;
  numero: string;
  article_vise: string;
  etat: string;
  sort: string;
  auteur_ref: string;
  auteur: AuteurInfo | null;
  auteur_type: string;
  auteur_nom: string | null;
  groupe_ref: string;
  groupe: { libelle: string; libelle_court: string } | null;
  groupe_nom: string | null;
  dispositif: string | null;
  expose_sommaire: string | null;
  date_depot: string | null;
  themes: string[];
  resume_ia: string | null;
  url_source: string | null;
}

export interface Amendement {
  uid: string;
  legislature: number;
  numero: string;
  texte_ref: string;
  organe_examen: string;
  auteur_ref: string;
  auteur_type: string;
  groupe_ref: string;
  article_vise: string;
  dispositif: string;
  expose_sommaire: string;
  date_depot: string | null;
  etat: string;
  sort: string;
  source: string;
  themes: string[];
  resume_ia: string | null;
  score_impact: { adoption_score: number } | null;
  created_at: string | null;
}

export interface Acteur {
  uid: string;
  civilite: string;
  prenom: string;
  nom: string;
  groupe_politique_ref: string;
  profession: string;
  date_naissance: string | null;
  email: string;
  telephone: string;
  telephone_2: string | null;
  site_web: string;
  twitter: string;
  facebook: string | null;
  instagram: string | null;
  linkedin: string | null;
  adresse_an: string | null;
  adresse_circo: string | null;
  collaborateurs: { nom: string; civilite: string }[];
  hatvp_url: string;
  source: string;
  groupe_politique?: {
    uid: string;
    libelle: string;
    libelle_court: string;
  };
  intelligence?: {
    stats: {
      nb_amendements: number;
      nb_adoptes: number;
      nb_rejetes: number;
      nb_retires: number;
      nb_tombes: number;
      taux_adoption: number;
    };
    adoption_par_theme: Record<
      string,
      { adoptes: number; total: number; taux_adoption: number }
    >;
    cosignataires_frequents: {
      uid: string;
      nom: string;
      groupe: string;
      nb_cosignatures: number;
    }[];
    activite_recente_30j: {
      uid: string;
      numero: string;
      sort: string;
      date_depot: string;
      texte_ref: string;
      texte_titre: string | null;
      article_vise: string | null;
      themes: string[];
      resume_ia: string | null;
    }[];
    textes_deposes: {
      uid: string;
      titre: string;
      type_code: string;
      denomination: string;
      date_depot: string | null;
      themes: string[];
      source: string;
    }[];
  };
}

export interface Signal {
  id: number;
  signal_type: string;
  severity: string;
  title: string;
  description: string;
  themes: string[];
  texte_ref: string;
  amendement_refs: string[];
  data_snapshot: Record<string, unknown>;
  is_read: boolean;
  is_dismissed: boolean;
  created_at: string | null;
}

export interface AdoptionBreakdown {
  score: number;
  auteur: { rate: number; adopted: number; total: number; weight: number };
  groupe: { rate: number; adopted: number; total: number; weight: number };
  commission: { rate: number; adopted: number; total: number; weight: number };
  gouvernement: { is_gouvernement: boolean; score: number; weight: number };
}

export interface AlertAmendement {
  uid: string;
  numero: string;
  article_vise: string | null;
  etat: string | null;
  sort: string | null;
  date_depot: string | null;
  themes: string[];
  resume_ia: string | null;
  expose_sommaire: string | null;
  url_source: string | null;
  auteur: AuteurInfo | null;
  auteur_nom: string | null;
  groupe: OrganeInfo | null;
  groupe_nom: string | null;
  adoption_score: number | null;
  adoption_breakdown: AdoptionBreakdown | null;
  cosignataires: AuteurInfo[];
  nb_groupes_differents: number;
  convergence_transpartisane: boolean;
  auteur_stats?: {
    nb_amendements: number;
    nb_adoptes: number;
    taux_adoption: number;
  };
}

export interface AlertAction {
  type: string; // "draft_note" | "draft_email" | "draft_amendment" | "monitor"
  label: string;
  agent_prompt: string | null;
}

export interface ImpactAlert {
  id: number;
  profile_id: number;
  impact_level: string;
  impact_summary: string;
  exposure_eur: number;
  matched_themes: string[];
  actions: AlertAction[];
  actions_status: Record<string, string>;
  is_threat: boolean;
  is_read: boolean;
  texte_uid: string | null;
  amendement_uid: string | null;
  reunion_uid: string | null;
  compte_rendu_uid: string | null;
  created_at: string | null;
  amendement?: AlertAmendement;
}

export interface DashboardData {
  stats: {
    urgent: number;
    watch: number;
    exposure_eur: number;
  };
  signals: Signal[];
  recent_textes: Texte[];
  recent_amendements: Amendement[];
  upcoming_reunions: unknown[];
}

export interface ProfileDetail {
  id: number;
  name: string;
  email: string;
  sectors: string[];
  business_lines?: string[];
  regulatory_focus?: string[];
  context_note: string;
  is_active: boolean;
  stats: {
    total_alertes: number;
    non_lues: number;
    urgentes: number;
    par_niveau: Record<string, number>;
    menaces: number;
    opportunites: number;
    exposure_eur: number;
  };
}

export interface SearchResult {
  query: string;
  results: {
    textes: unknown[];
    amendements: unknown[];
    acteurs: unknown[];
    reunions: unknown[];
  };
  counts: {
    textes: number;
    amendements: number;
    acteurs: number;
    reunions: number;
    total: number;
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a query-string from a params object, omitting undefined/null values. */
function buildQueryString(params?: Record<string, unknown>): string {
  if (!params) return "";
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null) {
      searchParams.append(key, String(value));
    }
  }
  const qs = searchParams.toString();
  return qs ? `?${qs}` : "";
}

/** Generic fetch wrapper that throws on non-OK responses. */
async function apiFetch<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const url = `${API_BASE}${path}${buildQueryString(params)}`;
  const headers: Record<string, string> = {};
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("legix_token");
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }
  const response = await fetch(url, { headers });
  if (!response.ok) {
    throw new Error(`API error ${response.status}: ${response.statusText} (${url})`);
  }
  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function fetchDashboard(): Promise<DashboardData> {
  return apiFetch<DashboardData>("/dashboard");
}

export async function fetchTextes(
  params?: Record<string, unknown>,
): Promise<Texte[]> {
  return apiFetch<Texte[]>("/textes", params);
}

export async function fetchTexte(uid: string): Promise<Texte> {
  return apiFetch<Texte>(`/textes/${uid}`);
}

export async function fetchAmendements(
  params?: Record<string, unknown>,
): Promise<Amendement[]> {
  return apiFetch<Amendement[]>("/amendements", params);
}

export interface ActeurListItem extends Acteur {
  stats?: {
    nb_amendements: number;
    nb_adoptes: number;
    taux_adoption: number;
  };
}

export interface ActeurListResponse {
  items: ActeurListItem[];
  total: number;
}

export interface GroupeInfo {
  uid: string;
  libelle: string;
  libelle_court: string;
  nb_deputes: number;
}

export async function fetchActeurs(
  params?: Record<string, unknown>,
): Promise<ActeurListResponse> {
  return apiFetch<ActeurListResponse>("/acteurs", params);
}

export async function fetchGroupes(): Promise<GroupeInfo[]> {
  return apiFetch<GroupeInfo[]>("/acteurs/groupes");
}

// Cartographie
export interface GraphNode {
  uid: string;
  label: string;
  groupe_uid: string;
  groupe_court: string;
  groupe_label: string;
  nb_amendements: number;
  adoption_rate: number;
  nb_adopted: number;
  x: number;
  y: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
  types: string[];
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  meta: {
    total_nodes: number;
    total_edges: number;
    edge_types: Record<string, number>;
  };
}

export interface CartoStats {
  top_deputies: {
    uid: string;
    label: string;
    groupe_court: string;
    nb_connections: number;
    nb_amendements: number;
    adoption_rate: number;
  }[];
  group_stats: {
    libelle_court: string;
    nb_deputes_in_graph: number;
    nb_internal_edges: number;
    nb_external_edges: number;
  }[];
}

export interface GroupeStats {
  uid: string;
  libelle: string;
  libelle_court: string;
  nb_deputes: number;
  nb_amendements: number;
  taux_adoption: number;
}

export interface SecteurData {
  theme: string;
  period_days: number;
  textes: unknown[];
  deputes_cles: {
    uid: string;
    nom: string;
    groupe: string;
    nb_amdts_secteur: number;
    nb_adoptes_secteur: number;
    taux_adoption_secteur: number;
  }[];
  reunions: unknown[];
  stats: {
    taux_adoption: number;
    nb_textes: number;
    nb_amendements: number;
    nb_adoptes: number;
    nb_reunions_avenir: number;
  };
}

export async function fetchCartoGraph(params?: Record<string, unknown>): Promise<GraphData> {
  return apiFetch<GraphData>("/cartographie/graph", params);
}

export async function fetchCartoStats(params?: Record<string, unknown>): Promise<CartoStats> {
  return apiFetch<CartoStats>("/cartographie/stats", params);
}

export async function fetchCartoGroupes(): Promise<GroupeStats[]> {
  return apiFetch<GroupeStats[]>("/cartographie/groupes");
}

export async function fetchCartoSecteur(theme: string, params?: Record<string, unknown>): Promise<SecteurData> {
  return apiFetch<SecteurData>(`/cartographie/secteur/${encodeURIComponent(theme)}`, params);
}

export async function fetchCartoDepute(uid: string, params?: Record<string, unknown>): Promise<unknown> {
  return apiFetch<unknown>(`/cartographie/depute/${uid}`, params);
}

export async function fetchActeur(uid: string): Promise<Acteur> {
  return apiFetch<Acteur>(`/acteurs/${uid}`);
}

export async function fetchSignaux(
  params?: Record<string, unknown>,
): Promise<Signal[]> {
  return apiFetch<Signal[]>("/signaux", params);
}

export async function fetchAlertes(
  params?: Record<string, unknown>,
): Promise<ImpactAlert[]> {
  return apiFetch<ImpactAlert[]>("/alertes", params);
}

export async function fetchAlerte(id: number): Promise<ImpactAlert> {
  return apiFetch<ImpactAlert>(`/alertes/${id}`);
}

export async function updateActionStatus(
  alertId: number,
  actionIndex: number,
  status: string,
): Promise<{ status: string; actions_status: Record<string, string> }> {
  const url = `${API_BASE}/alertes/${alertId}/actions/${actionIndex}`;
  const response = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!response.ok) {
    throw new Error(`API error ${response.status}`);
  }
  return response.json();
}

export async function searchAll(q: string): Promise<SearchResult> {
  return apiFetch<SearchResult>("/search", { q });
}

export async function fetchStats(): Promise<unknown> {
  return apiFetch<unknown>("/stats");
}

// ---------------------------------------------------------------------------
// Profiles
// ---------------------------------------------------------------------------

export async function fetchProfileDetail(id: number): Promise<ProfileDetail> {
  return apiFetch<ProfileDetail>(`/profiles/${id}`);
}

export async function fetchProfileAlertes(
  id: number,
  params?: Record<string, unknown>,
): Promise<ImpactAlert[]> {
  return apiFetch<ImpactAlert[]>(`/profiles/${id}/alertes`, params);
}

// ---------------------------------------------------------------------------
// Textes suivis (TexteBriefs)
// ---------------------------------------------------------------------------

export interface ForceMapEntry {
  groupe: string;
  groupe_uid: string;
  nb_amendements: number;
  nb_adoptes: number;
  position: "pour" | "contre" | "mixte";
  analyse: string;
}

export interface CriticalAmendment {
  uid: string;
  numero: string;
  auteur: string;
  groupe: string;
  resume: string;
  adoption_score: number;
  why_critical: string;
}

export interface KeyContact {
  uid: string;
  nom: string;
  groupe: string;
  nb_amendements: number;
  taux_adoption: number;
  why_relevant: string;
}

export interface ActionPlanItem {
  priority: number;
  action: string;
  deadline: string;
  who: string;
}

export interface TexteBrief {
  id: number;
  profile_id: number;
  texte_uid: string;
  followup_id: number | null;
  executive_summary: string;
  force_map: ForceMapEntry[];
  critical_amendments: CriticalAmendment[];
  key_contacts: KeyContact[];
  action_plan: ActionPlanItem[];
  exposure_eur: number | null;
  impact_level: string;
  is_threat: boolean;
  nb_amendements_analyzed: number;
  nb_groupes: number;
  nb_deputes: number;
  version: number;
  created_at: string | null;
  updated_at: string | null;
  texte?: {
    uid: string;
    titre: string;
    type_code: string;
    source: string;
    date_depot: string | null;
    themes: string[];
    resume_ia: string | null;
  };
  followup?: {
    id: number;
    status: string;
    priority: string;
    change_log: unknown[];
    next_check_at: string | null;
  };
  nb_amendements_total?: number;
}

export async function fetchTextesSuivis(profileId: number): Promise<TexteBrief[]> {
  return apiFetch<TexteBrief[]>(`/profiles/${profileId}/textes-suivis`);
}

export async function fetchTexteBrief(
  profileId: number,
  texteUid: string,
): Promise<TexteBrief> {
  return apiFetch<TexteBrief>(`/profiles/${profileId}/textes-suivis/${texteUid}`);
}

export async function refreshTexteBrief(
  profileId: number,
  texteUid: string,
): Promise<TexteBrief> {
  const url = `${API_BASE}/profiles/${profileId}/textes-suivis/${texteUid}/refresh`;
  const response = await fetch(url, { method: "POST" });
  if (!response.ok) throw new Error(`API error ${response.status}`);
  return response.json();
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

export interface ActionTask {
  id: number;
  profile_id: number;
  alert_id: number | null;
  texte_uid: string | null;
  action_type: string;
  label: string;
  rationale: string | null;
  priority: number | null;
  target_acteur_uids: string[];
  status: string; // "pending" | "in_progress" | "completed"
  result_content: string | null;
  result_format: string | null;
  due_date: string | null;
  completed_at: string | null;
  created_at: string | null;
  livrables?: LivrableOut[];
}

export interface LivrableOut {
  id: number;
  action_id: number;
  profile_id: number;
  type: string; // note_comex / email / amendement / fiche_position
  title: string;
  content: string | null;
  format: string;
  status: string; // draft / final / sent
  metadata: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface EvenementOut {
  id: string;
  type: string; // amendement / vote / declaration / presse / commission / signal / alerte / suivi
  title: string;
  description: string | null;
  severity: string; // info / warning / critical
  source_ref: string | null;
  source_url: string | null;
  date: string | null;
}

export interface ActeurInfluence {
  uid: string;
  nom: string;
  groupe: string | null;
  influence_score: number;
  breakdown: {
    amendements: { score: number; count: number; weight: number };
    adoption: { score: number; rate: number; adopted: number; total: number; weight: number };
    commissions: { score: number; weight: number };
    convergence: { score: number; cosignatures: number; groupes_differents: number; weight: number };
  };
  nb_amendements_dossier?: number;
  taux_adoption_dossier?: number;
  why_relevant?: string;
}

export async function fetchActions(
  params?: Record<string, unknown>,
): Promise<ActionTask[]> {
  return apiFetch<ActionTask[]>("/actions", params);
}

export async function executeAction(taskId: number): Promise<ActionTask> {
  const url = `${API_BASE}/actions/${taskId}/execute`;
  const headers: Record<string, string> = {};
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("legix_token");
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const response = await fetch(url, { method: "POST", headers });
  if (!response.ok) throw new Error(`API error ${response.status}`);
  return response.json();
}

// ---------------------------------------------------------------------------
// Dossiers enrichis — actions, evenements, acteurs cles
// ---------------------------------------------------------------------------

export async function generateDossierActions(texteUid: string): Promise<ActionTask[]> {
  const url = `${API_BASE}/dossiers/${texteUid}/actions/generate`;
  const headers: Record<string, string> = {};
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("legix_token");
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const response = await fetch(url, { method: "POST", headers });
  if (!response.ok) throw new Error(`API error ${response.status}`);
  return response.json();
}

export async function fetchDossierActions(texteUid: string): Promise<ActionTask[]> {
  return apiFetch<ActionTask[]>(`/dossiers/${texteUid}/actions`);
}

export async function fetchDossierEvenements(
  texteUid: string,
  params?: Record<string, unknown>,
): Promise<EvenementOut[]> {
  return apiFetch<EvenementOut[]>(`/dossiers/${texteUid}/evenements`, params);
}

export async function fetchDossierActeursCles(
  texteUid: string,
  params?: Record<string, unknown>,
): Promise<ActeurInfluence[]> {
  return apiFetch<ActeurInfluence[]>(`/dossiers/${texteUid}/acteurs-cles`, params);
}

// ---------------------------------------------------------------------------
// Livrables
// ---------------------------------------------------------------------------

export async function generateLivrable(
  actionId: number,
  type: string,
): Promise<LivrableOut> {
  const url = `${API_BASE}/actions/${actionId}/generate-livrable`;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("legix_token");
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const response = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify({ type }),
  });
  if (!response.ok) throw new Error(`API error ${response.status}`);
  return response.json();
}

export async function fetchLivrable(id: number): Promise<LivrableOut> {
  return apiFetch<LivrableOut>(`/livrables/${id}`);
}

export async function updateLivrable(
  id: number,
  data: { status?: string; content?: string; title?: string },
): Promise<LivrableOut> {
  const url = `${API_BASE}/livrables/${id}`;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("legix_token");
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const response = await fetch(url, {
    method: "PUT",
    headers,
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error(`API error ${response.status}`);
  return response.json();
}

export async function fetchActeurInfluence(uid: string): Promise<ActeurInfluence> {
  return apiFetch<ActeurInfluence>(`/acteurs/${uid}/influence`);
}

// ---------------------------------------------------------------------------
// Streaming livrable generation
// ---------------------------------------------------------------------------

export interface StreamEvent {
  type: "init" | "delta" | "done" | "error" | "status";
  text?: string;
  livrable_id?: number;
  title?: string;
  content_length?: number;
  message?: string;
}

export function streamGenerateLivrable(
  actionId: number,
  type: string,
  onEvent: (event: StreamEvent) => void,
): AbortController {
  const controller = new AbortController();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("legix_token");
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  fetch(`${API_BASE}/actions/${actionId}/generate-livrable/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({ type }),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        onEvent({ type: "error", message: `API error ${response.status}` });
        return;
      }
      const reader = response.body?.getReader();
      if (!reader) return;
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const event = JSON.parse(line.slice(6)) as StreamEvent;
              onEvent(event);
            } catch {
              /* skip malformed */
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== "AbortError") {
        onEvent({ type: "error", message: err.message });
      }
    });

  return controller;
}

// ---------------------------------------------------------------------------
// Send email with livrable
// ---------------------------------------------------------------------------

export interface EmailPrepared {
  status: string;
  to: string;
  subject: string;
  body: string;
  pdf_filename: string;
  pdf_base64: string;
  pdf_size_bytes: number;
  mailto_link: string;
}

export async function sendLivrableEmail(
  livrableId: number,
  to: string,
  subject?: string,
): Promise<EmailPrepared> {
  const url = `${API_BASE}/livrables/${livrableId}/send-email`;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("legix_token");
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const response = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify({ to, subject, attach_pdf: true }),
  });
  if (!response.ok) throw new Error(`API error ${response.status}`);
  return response.json();
}

// ---------------------------------------------------------------------------
// Followups
// ---------------------------------------------------------------------------

export interface FollowUp {
  id: number;
  profile_id: number;
  texte_uid: string;
  status: string;
  priority: string;
  change_log: { date: string; event: string; detail: string }[];
  next_check_at: string | null;
  commission_date: string | null;
  notes: string | null;
}

export async function fetchFollowups(
  params?: Record<string, unknown>,
): Promise<FollowUp[]> {
  return apiFetch<FollowUp[]>("/followups", params);
}

// ---------------------------------------------------------------------------
// Briefings
// ---------------------------------------------------------------------------

export interface BriefingOut {
  id: number;
  profile_id: number;
  title: string;
  content: string;
  created_at: string | null;
}

export async function fetchBriefings(): Promise<BriefingOut[]> {
  return apiFetch<BriefingOut[]>("/briefings");
}

export async function generateBriefing(): Promise<BriefingOut> {
  const url = `${API_BASE}/briefings/generate`;
  const response = await fetch(url, { method: "POST" });
  if (!response.ok) throw new Error(`API error ${response.status}`);
  return response.json();
}
