"""Modèles ORM — SQLAlchemy 2.0 async.

Adapté depuis LegisAPI avec extensions pour LegiX :
- Tables documents : Texte, Amendement, Reunion, CompteRendu
- Tables acteurs : Acteur, Organe
- Tables enrichissement : Signal, SeenPublication
- Tables client : ClientProfile, Briefing
- Tables agent proactif : TexteFollowUp, TexteBrief, ActionTask, NotificationQueue, PipelineRun
- Tables livrables : Livrable, Evenement
- Tables association : amendement_cosignataires, texte_auteurs
- Tables anticipation : AnticipationReport
- Tables stakeholders : StakeholderProfile, StakeholderDossierLink, ContactInteraction
- Tables presse : PressArticle
- Tables client knowledge : ClientDocument
- Tables parlementaires : QuestionParlementaire, ScrutinVote
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# --- Tables d'association ---

amendement_cosignataires = Table(
    "amendement_cosignataires",
    Base.metadata,
    Column("amendement_uid", String, ForeignKey("amendements.uid"), primary_key=True),
    Column("acteur_uid", String, ForeignKey("acteurs.uid"), primary_key=True),
)

texte_auteurs = Table(
    "texte_auteurs",
    Base.metadata,
    Column("texte_uid", String, ForeignKey("textes.uid"), primary_key=True),
    Column("acteur_uid", String, ForeignKey("acteurs.uid"), primary_key=True),
)


# --- Documents parlementaires ---


class Texte(Base):
    __tablename__ = "textes"

    uid = Column(String, primary_key=True)
    legislature = Column(Integer)
    denomination = Column(String)  # "Proposition de loi", "Projet de loi"...
    titre = Column(Text)
    titre_court = Column(String)
    type_code = Column(String)  # PION, PRJL, PNRE...
    type_libelle = Column(String)
    date_depot = Column(DateTime)
    date_publication = Column(DateTime)
    dossier_ref = Column(String)
    organe_ref = Column(String)  # Commission de renvoi
    source = Column(String, default="assemblee")
    url_source = Column(String)
    auteur_texte = Column(String)  # Auteur en texte libre (Sénat)

    # Enrichissement IA
    themes = Column(Text)  # JSON list
    resume_ia = Column(Text)
    score_impact = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    amendements = relationship("Amendement", back_populates="texte")
    auteurs = relationship("Acteur", secondary=texte_auteurs)


class Amendement(Base):
    __tablename__ = "amendements"

    uid = Column(String, primary_key=True)
    legislature = Column(Integer)
    numero = Column(String)  # "CL30", "AS8"...
    numero_ordre_depot = Column(Integer)
    texte_ref = Column(String, ForeignKey("textes.uid"))
    examen_ref = Column(String)
    organe_examen = Column(String)  # "CION_LOIS", "AN"...

    # Auteur
    auteur_ref = Column(String, ForeignKey("acteurs.uid"))
    auteur_type = Column(String)  # "Député", "Gouvernement"
    groupe_ref = Column(String, ForeignKey("organes.uid"))

    # Contenu
    article_vise = Column(String)  # "Article 8"
    article_type = Column(String)  # "ARTICLE", "TITRE"...
    alinea = Column(String)
    dispositif = Column(Text)  # HTML du dispositif
    expose_sommaire = Column(Text)  # HTML de l'exposé des motifs

    # Cycle de vie
    date_depot = Column(DateTime)
    date_publication = Column(DateTime)
    date_sort = Column(DateTime)
    etat = Column(String)  # "En traitement", "Adopté"...
    sort = Column(String)  # "Adopté", "Rejeté", "Retiré"...

    source = Column(String, default="assemblee")
    url_source = Column(String)
    auteur_nom = Column(String)  # Nom auteur texte libre (Sénat)
    groupe_nom = Column(String)  # Nom groupe texte libre (Sénat)

    # Enrichissement IA
    themes = Column(Text)
    resume_ia = Column(Text)
    score_impact = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    texte = relationship("Texte", back_populates="amendements")
    auteur = relationship("Acteur", foreign_keys=[auteur_ref])
    groupe = relationship("Organe", foreign_keys=[groupe_ref])
    cosignataires = relationship("Acteur", secondary=amendement_cosignataires)


class Acteur(Base):
    __tablename__ = "acteurs"

    uid = Column(String, primary_key=True)
    civilite = Column(String)
    prenom = Column(String)
    nom = Column(String)
    groupe_politique_ref = Column(String, ForeignKey("organes.uid"))
    profession = Column(String)
    date_naissance = Column(DateTime)
    email = Column(String)
    telephone = Column(String)
    telephone_2 = Column(String)
    site_web = Column(String)
    twitter = Column(String)
    facebook = Column(String)
    instagram = Column(String)
    linkedin = Column(String)
    adresse_an = Column(String)
    adresse_circo = Column(String)
    collaborateurs = Column(String)  # JSON : [{"nom":"...", "civilite":"..."}]
    hatvp_url = Column(String)
    source = Column(String, default="assemblee")

    # Scoring d'influence
    influence_score = Column(Float)  # Score global 0-100
    commissions = Column(Text)  # JSON list des commissions actives
    specialites = Column(Text)  # JSON: themes d'expertise (derives des amendements)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    groupe_politique = relationship("Organe", foreign_keys=[groupe_politique_ref])


class Organe(Base):
    __tablename__ = "organes"

    uid = Column(String, primary_key=True)
    type_code = Column(String)  # "GP", "COMPER", "DELEG"...
    type_libelle = Column(String)
    libelle = Column(String)
    libelle_court = Column(String)
    date_debut = Column(DateTime)
    date_fin = Column(DateTime)
    legislature = Column(Integer)
    source = Column(String, default="assemblee")

    created_at = Column(DateTime, default=datetime.utcnow)


class Reunion(Base):
    __tablename__ = "reunions"

    uid = Column(String, primary_key=True)
    date_debut = Column(DateTime)
    lieu = Column(String)
    organe_ref = Column(String, ForeignKey("organes.uid"))
    etat = Column(String)  # "Confirmé", "Annulé", "Éventuel"
    ouverture_presse = Column(Boolean)
    captation_video = Column(Boolean)
    visioconference = Column(Boolean)
    odj = Column(Text)  # JSON list des items d'ordre du jour
    format_reunion = Column(String)
    source = Column(String, default="assemblee")
    url_source = Column(String)
    commission_nom = Column(String)  # Nom commission texte libre (Sénat)

    # Enrichissement IA
    themes = Column(Text)
    resume_ia = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    organe = relationship("Organe")


class CompteRendu(Base):
    __tablename__ = "comptes_rendus"

    uid = Column(String, primary_key=True)
    seance_ref = Column(String)
    session_ref = Column(String)
    date_seance = Column(DateTime)
    date_seance_jour = Column(String)  # "mardi 03 février 2026"
    num_seance = Column(Integer)
    etat = Column(String)  # "complet", "provisoire"
    sommaire = Column(Text)  # JSON list des sujets
    source = Column(String, default="assemblee")
    url_source = Column(String)

    # Enrichissement IA
    themes = Column(Text)
    resume_ia = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# --- Signaux et veille ---


class Signal(Base):
    """Signal faible détecté dans l'activité parlementaire."""

    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_type = Column(String, nullable=False)
    severity = Column(String, nullable=False, default="medium")
    title = Column(String, nullable=False)
    description = Column(Text)
    themes = Column(Text)  # JSON list
    texte_ref = Column(String)
    amendement_refs = Column(Text)  # JSON list d'UIDs
    data_snapshot = Column(Text)  # JSON données brutes
    is_read = Column(Boolean, default=False)
    is_dismissed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class SeenPublication(Base):
    """Déduplication des publications déjà traitées."""

    __tablename__ = "seen_publications"

    url = Column(String, primary_key=True)
    timestamp = Column(String)
    document_type = Column(String)
    document_uid = Column(String)
    first_seen = Column(DateTime, default=datetime.utcnow)


# --- Clients et personnalisation ---


class ClientProfile(Base):
    """Profil client pour la personnalisation des feeds et briefings."""

    __tablename__ = "client_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    email = Column(String)
    sectors = Column(Text)  # JSON list : ["santé", "énergie", "numérique"]
    business_lines = Column(Text)  # JSON list : ["Pharma innovante", "Vaccins", "CHC"]
    products = Column(Text)  # JSON list : ["Dupixent", "Doliprane", "Kevzara"]
    regulatory_focus = Column(Text)  # JSON list : ["AMM", "prix du médicament", "PFAS"]
    followed_textes = Column(Text)  # JSON list d'UIDs
    followed_deputes = Column(Text)  # JSON list d'UIDs
    followed_groupes = Column(Text)  # JSON list d'UIDs
    followed_commissions = Column(Text)  # JSON list d'UIDs
    telegram_chat_id = Column(String)
    context_note = Column(Text)  # "Cabinet spécialisé pharma, focus PFAS et AMM"

    # Auth
    password_hash = Column(String)

    # Données publiques entreprise (API SIRENE / enrichissement)
    siren = Column(String)
    chiffre_affaires = Column(Float)  # CA annuel EUR
    resultat_net = Column(Float)  # Résultat net EUR
    effectifs = Column(String)  # Tranche effectifs
    dirigeants = Column(Text)  # JSON liste dirigeants
    code_naf = Column(String)  # Code NAF/APE
    siege_social = Column(String)  # Adresse siège
    site_web = Column(String)  # URL site
    categorie_entreprise = Column(String)  # PME/ETI/GE
    description = Column(Text)  # Description activité (Claude)
    monitoring_explanation = Column(Text)  # Explication de ce que LegiX surveille
    key_risks = Column(Text)  # JSON list : risques réglementaires identifiés
    key_opportunities = Column(Text)  # JSON list : opportunités réglementaires

    # --- Configuration de veille personnalisée par client ---
    # Chaque client a son propre périmètre de surveillance

    # Mots-clés de veille (presse, rapports, débats)
    watch_keywords = Column(Text)  # JSON list : ["PFAS", "prix du médicament", "AMM européenne"]
    watch_keywords_exclude = Column(Text)  # JSON list : mots-clés à ignorer

    # Concurrents à surveiller (mentions presse, positions PA)
    competitors = Column(Text)  # JSON list : ["Novartis", "Pfizer", "Roche"]

    # Think tanks et sources d'anticipation pertinents
    watched_think_tanks = Column(Text)  # JSON list : ["Institut Montaigne", "France Stratégie"]
    watched_inspections = Column(Text)  # JSON list : ["Cour des Comptes", "IGAS"]

    # ONG et parties prenantes à surveiller (spécifique au secteur)
    watched_ngos = Column(Text)  # JSON list : ["UFC-Que Choisir", "France Assos Santé"] ou ["WWF", "Greenpeace"]
    watched_federations = Column(Text)  # JSON list : ["LEEM", "FEFIS"] ou ["MEDEF", "CPME"]
    watched_media = Column(Text)  # JSON list : ["Contexte Santé", "APMnews"] ou ["Contexte Énergie"]

    # Journalistes clés à suivre (propre à chaque client)
    watched_journalists = Column(Text)  # JSON list : [{"nom": "...", "media": "...", "theme": "..."}]

    # Acteurs politiques à surveiller spécifiquement (au-delà des commissions)
    watched_politicians = Column(Text)  # JSON list d'UIDs ou noms : rapporteurs, ministres, etc.

    # Régulateurs pertinents (pas tous les 10, juste ceux du secteur)
    watched_regulators = Column(Text)  # JSON list : ["ANSM", "HAS"] ou ["CRE", "ADEME"]

    # Thématiques EU spécifiques
    eu_watch_keywords = Column(Text)  # JSON list : ["REACH", "PFAS", "pharmacovigilance"]
    eu_watched_committees = Column(Text)  # JSON list : ["ENVI", "ITRE"] (commissions PE)

    # Stratégie PA en cours (contexte pour les agents)
    pa_strategy = Column(Text)  # Texte libre : "Focus Q1 sur réforme AMM, coalition avec LEEM"
    pa_priorities = Column(Text)  # JSON list ordonnée : ["Réforme AMM", "PFAS", "Prix médicament"]

    # Préférences de notification
    telegram_bot_enabled = Column(Boolean, default=False)
    email_digest_enabled = Column(Boolean, default=True)
    email_digest_schedule = Column(String, default="daily")  # daily/weekly
    notification_hours = Column(String, default="08:00-20:00")

    receive_briefing = Column(Boolean, default=True)
    briefing_frequency = Column(String, default="daily")
    min_signal_severity = Column(String, default="medium")
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    briefings = relationship("Briefing", back_populates="profile")


class Briefing(Base):
    """Briefing personnalisé généré par l'IA."""

    __tablename__ = "briefings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"), nullable=False)
    title = Column(String)
    content = Column(Text)  # JSON structuré
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    delivered_dashboard = Column(Boolean, default=False)
    delivered_telegram = Column(Boolean, default=False)
    delivered_email = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("ClientProfile", back_populates="briefings")


# --- Tables LegiX spécifiques ---


class ImpactAlert(Base):
    """Alerte d'impact réglementaire personnalisée."""

    __tablename__ = "impact_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"))

    # Référence document source
    texte_uid = Column(String, ForeignKey("textes.uid"))
    amendement_uid = Column(String, ForeignKey("amendements.uid"))
    reunion_uid = Column(String, ForeignKey("reunions.uid"))
    compte_rendu_uid = Column(String, ForeignKey("comptes_rendus.uid"))

    impact_level = Column(String, nullable=False)  # low/medium/high/critical
    impact_summary = Column(Text)  # Résumé IA de l'impact
    exposure_eur = Column(Float)  # Exposition financière estimée en EUR
    matched_themes = Column(Text)  # JSON list des thèmes en commun
    action_required = Column(Text)  # JSON list d'actions structurees
    is_threat = Column(Boolean, default=True)  # True=menace, False=opportunité
    actions_status = Column(Text)  # JSON: {"0": "done", "1": "pending", ...}

    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("ClientProfile")
    texte = relationship("Texte")
    amendement = relationship("Amendement")
    reunion = relationship("Reunion")
    compte_rendu = relationship("CompteRendu")


class OnboardingJob(Base):
    """Suivi de la génération d'alertes lors de l'onboarding."""

    __tablename__ = "onboarding_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"), nullable=False)
    status = Column(String, nullable=False, default="pending")  # pending/enriching/generating/completed/failed
    progress_current = Column(Integer, default=0)
    progress_total = Column(Integer, default=0)
    alerts_count = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    profile = relationship("ClientProfile")


# --- Agent proactif ---


class TexteFollowUp(Base):
    """Suivi proactif d'un texte dans le temps pour un client."""

    __tablename__ = "texte_followups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"), nullable=False)
    texte_uid = Column(String, ForeignKey("textes.uid"), nullable=False)
    status = Column(String, default="watching")  # watching/escalated/resolved/archived
    priority = Column(String, default="medium")  # low/medium/high/critical
    last_analysis = Column(Text)  # JSON : snapshot dernière analyse agent
    change_log = Column(Text)  # JSON list : [{"date": ..., "event": ..., "detail": ...}]
    next_check_at = Column(DateTime)  # Prochaine date de re-analyse
    commission_date = Column(DateTime)  # Date commission connue
    notes = Column(Text)  # Notes utilisateur
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("ClientProfile")
    texte = relationship("Texte")
    brief = relationship("TexteBrief", uselist=False, back_populates="followup")


class TexteBrief(Base):
    """Analyse consolidee d'un texte pour un client.

    Contient le dossier complet : resume executif, cartographie des forces,
    amendements critiques, contacts cles, plan d'action.
    Regenere periodiquement quand de nouveaux amendements arrivent.
    """

    __tablename__ = "texte_briefs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"), nullable=False)
    texte_uid = Column(String, ForeignKey("textes.uid"), nullable=False)
    followup_id = Column(Integer, ForeignKey("texte_followups.id"))

    # Contenu analytique (JSON sauf executive_summary)
    executive_summary = Column(Text)  # Markdown
    force_map = Column(Text)  # JSON: [{"groupe", "nb_amendements", "position", "analyse"}]
    critical_amendments = Column(Text)  # JSON: [{"uid", "numero", "resume", "adoption_score", "why_critical"}]
    key_contacts = Column(Text)  # JSON: [{"uid", "nom", "groupe", "nb_amendements", "taux_adoption", "why_relevant"}]
    action_plan = Column(Text)  # JSON: [{"priority", "action", "deadline", "who"}]
    exposure_eur = Column(Float)
    impact_level = Column(String)  # low/medium/high/critical
    is_threat = Column(Boolean, default=True)

    # Metadonnees
    nb_amendements_analyzed = Column(Integer, default=0)
    nb_groupes = Column(Integer, default=0)
    nb_deputes = Column(Integer, default=0)
    version = Column(Integer, default=1)
    raw_agent_response = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("ClientProfile")
    texte = relationship("Texte")
    followup = relationship("TexteFollowUp", back_populates="brief")


class ActionTask(Base):
    """Tâche d'action avec exécution par agent rédacteur."""

    __tablename__ = "action_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"), nullable=False)
    alert_id = Column(Integer, ForeignKey("impact_alerts.id"))
    texte_uid = Column(String, ForeignKey("textes.uid"), nullable=True)
    action_type = Column(String, nullable=False)  # draft_note/draft_email/draft_amendment/monitor
    label = Column(String, nullable=False)
    agent_prompt = Column(Text)  # Prompt pour le RedacteurAgent
    rationale = Column(Text)  # Explication IA du pourquoi
    priority = Column(Integer, default=3)  # 1=urgent, 5=faible
    target_acteur_uids = Column(Text)  # JSON list d'UIDs acteurs cibles
    status = Column(String, default="pending")  # pending/in_progress/completed/failed
    result_content = Column(Text)  # Contenu généré (markdown)
    result_format = Column(String, default="markdown")  # markdown/html
    due_date = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("ClientProfile")
    alert = relationship("ImpactAlert")
    texte = relationship("Texte")
    livrables = relationship("Livrable", back_populates="action")


class NotificationQueue(Base):
    """File d'attente de notifications (Telegram, email)."""

    __tablename__ = "notification_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"), nullable=False)
    channel = Column(String, nullable=False)  # telegram/email
    priority = Column(String, default="normal")  # instant/normal/digest
    subject = Column(String)
    body = Column(Text, nullable=False)
    alert_id = Column(Integer, ForeignKey("impact_alerts.id"))
    briefing_id = Column(Integer, ForeignKey("briefings.id"))
    status = Column(String, default="pending")  # pending/sent/failed
    sent_at = Column(DateTime)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("ClientProfile")


class PipelineRun(Base):
    """Audit trail des exécutions du pipeline proactif."""

    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_type = Column(String, nullable=False)  # collect/enrich/detect/notify/briefing/full
    status = Column(String, default="running")  # running/completed/failed
    stats = Column(Text)  # JSON stats
    error_message = Column(Text)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


class Livrable(Base):
    """Document généré par un agent, lié à une action."""

    __tablename__ = "livrables"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action_id = Column(Integer, ForeignKey("action_tasks.id"))
    profile_id = Column(Integer, ForeignKey("client_profiles.id"))
    type = Column(String)  # note_comex / email / amendement / fiche_position / qa
    title = Column(String)
    content = Column(Text)  # Markdown
    format = Column(String, default="markdown")
    status = Column(String, default="draft")  # draft / final / sent
    metadata_ = Column("metadata", Text)  # JSON: destinataire, references, etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    action = relationship("ActionTask", back_populates="livrables")
    profile = relationship("ClientProfile")


class Evenement(Base):
    """Événement dans la timeline d'un dossier."""

    __tablename__ = "evenements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    texte_uid = Column(String, ForeignKey("textes.uid"))
    profile_id = Column(Integer, ForeignKey("client_profiles.id"), nullable=True)
    event_type = Column(String)  # amendement / vote / declaration / presse / commission / signal
    title = Column(String)
    description = Column(Text)
    severity = Column(String, default="info")  # info / warning / critical
    source_ref = Column(String)  # UID de l'amendement, reunion, etc.
    source_url = Column(String)
    data = Column(Text)  # JSON supplementaire
    created_at = Column(DateTime, default=datetime.utcnow)

    texte = relationship("Texte")


# --- Anticipation pré-législative ---


class AnticipationReport(Base):
    """Signal pré-législatif : rapport think tank, inspection, étude académique.

    Suit le pipeline : rapport → recommandation → proposition → débat → loi.
    """

    __tablename__ = "anticipation_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(String, nullable=False)  # think_tank / rapport_inspection / academic / consultation / avis_ce
    source_name = Column(String, nullable=False)  # "Cour des Comptes", "Institut Montaigne"
    title = Column(String, nullable=False)
    url = Column(String, unique=True)
    publication_date = Column(DateTime)
    author = Column(String)

    # Analyse IA
    themes = Column(Text)  # JSON list
    resume_ia = Column(Text)
    policy_recommendations = Column(Text)  # JSON list de recommandations extraites
    legislative_probability = Column(Float)  # 0-1 probabilité de devenir loi
    estimated_timeline = Column(String)  # "6 mois", "1-2 ans"
    impact_assessment = Column(Text)  # Évaluation d'impact IA

    # Lien vers législation éventuelle
    linked_texte_uids = Column(Text)  # JSON list — rempli quand le rapport mène à une loi
    pipeline_stage = Column(String, default="report")  # report / recommendation / proposition / debate / law

    # Pertinence client
    matched_sectors = Column(Text)  # JSON list
    matched_profile_ids = Column(Text)  # JSON list de profile_id concernés

    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# --- Stakeholders ---


class StakeholderProfile(Base):
    """Profil enrichi d'un stakeholder (député, journaliste, ONG, fédération, collaborateur)."""

    __tablename__ = "stakeholder_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    acteur_uid = Column(String, ForeignKey("acteurs.uid"), nullable=True)  # FK si parlementaire
    stakeholder_type = Column(String, nullable=False)  # depute / senateur / journaliste / ong / federation / collaborateur / regulateur
    nom = Column(String, nullable=False)
    prenom = Column(String)
    organisation = Column(String)  # Media, ONG, fédération
    titre = Column(String)  # "Rapporteur", "Chef de service", "Directeur PA"
    email = Column(String)
    telephone = Column(String)
    twitter = Column(String)
    linkedin = Column(String)
    site_web = Column(String)

    # Persona IA (construit par ProfilActeurAgent)
    bio_summary = Column(Text)  # Résumé biographique IA
    political_positioning = Column(Text)  # JSON: {"economic": "liberal", "environment": "moderate"}
    key_themes = Column(Text)  # JSON list des thèmes d'expertise
    past_positions = Column(Text)  # JSON list des positions connues
    influence_score = Column(Float)  # 0-100
    influence_breakdown = Column(Text)  # JSON détail du scoring

    # Interaction client
    last_contact_date = Column(DateTime)
    contact_history = Column(Text)  # JSON list d'interactions
    relationship_status = Column(String, default="unknown")  # ally / neutral / opponent / unknown

    # Données brutes pour construction persona
    publications = Column(Text)  # JSON list de publications
    votes_summary = Column(Text)  # JSON résumé patterns de vote
    media_appearances = Column(Text)  # JSON list apparitions médias

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    acteur = relationship("Acteur", foreign_keys=[acteur_uid])


class StakeholderDossierLink(Base):
    """Position d'un stakeholder sur un dossier, avec rôle et positionnement."""

    __tablename__ = "stakeholder_dossier_links"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stakeholder_id = Column(Integer, ForeignKey("stakeholder_profiles.id"), nullable=False)
    texte_uid = Column(String, ForeignKey("textes.uid"), nullable=True)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"), nullable=True)

    role = Column(String)  # rapporteur / auteur / opposant / allie / indecis / journaliste_couvre
    position = Column(String, default="inconnu")  # pour / contre / neutre / inconnu
    position_confidence = Column(Float)  # 0-1
    relevance_score = Column(Float)  # 0-100
    notes = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)

    stakeholder = relationship("StakeholderProfile")
    texte = relationship("Texte")


class ContactInteraction(Base):
    """Log CRM des interactions avec des stakeholders."""

    __tablename__ = "contact_interactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"), nullable=False)
    stakeholder_id = Column(Integer, ForeignKey("stakeholder_profiles.id"), nullable=False)

    interaction_type = Column(String, nullable=False)  # email_sent / meeting / call / event / lobby
    date = Column(DateTime, default=datetime.utcnow)
    subject = Column(String)
    notes = Column(Text)
    outcome = Column(String)  # positive / neutral / negative
    follow_up_needed = Column(Boolean, default=False)
    follow_up_date = Column(DateTime)
    dossier_texte_uid = Column(String, ForeignKey("textes.uid"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("ClientProfile")
    stakeholder = relationship("StakeholderProfile")


# --- Presse dédiée ---


class PressArticle(Base):
    """Article de presse avec analyse dédiée (sentiment, mentions, riposte)."""

    __tablename__ = "press_articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String, unique=True, nullable=False)
    title = Column(String)
    source_name = Column(String)  # "Le Monde", "Les Echos", "Contexte"
    author = Column(String)
    publication_date = Column(DateTime)
    excerpt = Column(Text)  # Extrait / chapô

    # Analyse IA
    themes = Column(Text)  # JSON list
    resume_ia = Column(Text)
    sentiment = Column(String)  # positive / negative / neutral / mixed
    mentioned_entities = Column(Text)  # JSON: {"companies": [], "politicians": [], "orgs": [], "laws": []}

    # Pertinence client
    matched_profile_ids = Column(Text)  # JSON list de profile_id mentionnés
    requires_response = Column(Boolean, default=False)
    response_urgency = Column(String)  # low / medium / high / critical
    response_status = Column(String, default="none")  # none / draft / sent

    # Lien dossier
    linked_texte_uids = Column(Text)  # JSON list de textes liés

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# --- Client knowledge base ---


class ClientDocument(Base):
    """Document interne client pour knowledge base RAG."""

    __tablename__ = "client_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("client_profiles.id"), nullable=False)
    doc_type = Column(String, nullable=False)  # position_paper / internal_note / email / communication / rapport / presentation
    title = Column(String, nullable=False)
    content = Column(Text)  # Texte complet extrait
    file_path = Column(String)
    file_name = Column(String)

    # Intelligence extraite
    themes = Column(Text)  # JSON list
    key_positions = Column(Text)  # JSON: positions extraites
    mentioned_stakeholders = Column(Text)  # JSON list
    summary = Column(Text)  # Résumé IA

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("ClientProfile")


# --- Questions parlementaires ---


class QuestionParlementaire(Base):
    """Question écrite ou orale au gouvernement."""

    __tablename__ = "questions_parlementaires"

    uid = Column(String, primary_key=True)
    type_question = Column(String)  # QE / QOSD / QG / QAG
    legislature = Column(Integer)
    numero = Column(String)
    auteur_uid = Column(String, ForeignKey("acteurs.uid"), nullable=True)
    auteur_nom = Column(String)
    groupe_ref = Column(String, ForeignKey("organes.uid"), nullable=True)
    ministere = Column(String)  # Ministère interrogé
    rubrique = Column(String)  # Rubrique thématique AN
    titre = Column(String)
    texte_question = Column(Text)
    date_depot = Column(DateTime)

    # Réponse
    texte_reponse = Column(Text)
    date_reponse = Column(DateTime)
    has_response = Column(Boolean, default=False)

    # Enrichissement IA
    themes = Column(Text)
    resume_ia = Column(Text)
    source = Column(String, default="assemblee")

    created_at = Column(DateTime, default=datetime.utcnow)

    auteur = relationship("Acteur", foreign_keys=[auteur_uid])
    groupe = relationship("Organe", foreign_keys=[groupe_ref])


class ScrutinVote(Base):
    """Vote nominatif sur un scrutin public."""

    __tablename__ = "scrutin_votes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scrutin_numero = Column(Integer, nullable=False)
    scrutin_titre = Column(String)
    scrutin_date = Column(DateTime)
    scrutin_type = Column(String)  # solennel / ordinaire
    texte_ref = Column(String, ForeignKey("textes.uid"), nullable=True)

    # Vote de l'acteur
    acteur_uid = Column(String, ForeignKey("acteurs.uid"), nullable=False)
    position = Column(String, nullable=False)  # pour / contre / abstention / non_votant
    groupe_ref = Column(String, ForeignKey("organes.uid"), nullable=True)

    # Résultat global du scrutin
    nombre_votants = Column(Integer)
    pour_total = Column(Integer)
    contre_total = Column(Integer)
    abstentions_total = Column(Integer)
    resultat = Column(String)  # adopte / rejete

    source = Column(String, default="assemblee")
    created_at = Column(DateTime, default=datetime.utcnow)

    acteur = relationship("Acteur", foreign_keys=[acteur_uid])
    groupe = relationship("Organe", foreign_keys=[groupe_ref])
