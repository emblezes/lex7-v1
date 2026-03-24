"""Routes cartographie des relations parlementaires.

Portage depuis LegisAPI : graphe force-directed, profil influence,
stats reseau, top deputes par secteur.
"""

import json
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from legix.api.deps import get_db
from legix.core.models import (
    Acteur,
    Amendement,
    Organe,
    Texte,
    Reunion,
    amendement_cosignataires,
    texte_auteurs,
)
from legix.enrichment.scoring import _adoption_rate

router = APIRouter()


# --- Force-directed layout ---


def _force_layout(nodes: list[dict], edges: list[dict], iterations: int = 80) -> None:
    """Layout force-directed simple (modifie les noeuds en place)."""
    if not nodes:
        return

    idx = {n["uid"]: i for i, n in enumerate(nodes)}
    n = len(nodes)

    repulsion = 500.0
    attraction = 0.01
    gravity = 0.05
    max_disp = 10.0
    cooling = 0.95

    # Initialiser en clusters par groupe
    groups = defaultdict(list)
    for node in nodes:
        groups[node.get("groupe_court", "")].append(node)
    angle_step = 2 * math.pi / max(len(groups), 1)
    for gi, (gname, gnodes) in enumerate(groups.items()):
        cx = 50 * math.cos(gi * angle_step)
        cy = 50 * math.sin(gi * angle_step)
        for node in gnodes:
            node["x"] = cx + random.uniform(-15, 15)
            node["y"] = cy + random.uniform(-15, 15)

    temp = max_disp

    for _ in range(iterations):
        dx_arr = [0.0] * n
        dy_arr = [0.0] * n

        for i in range(n):
            for j in range(i + 1, n):
                ddx = nodes[i]["x"] - nodes[j]["x"]
                ddy = nodes[i]["y"] - nodes[j]["y"]
                dist = math.sqrt(ddx * ddx + ddy * ddy) + 0.01
                if dist > 200:
                    continue
                force = repulsion / (dist * dist)
                fx = ddx / dist * force
                fy = ddy / dist * force
                dx_arr[i] += fx
                dy_arr[i] += fy
                dx_arr[j] -= fx
                dy_arr[j] -= fy

        for e in edges:
            si = idx.get(e["source"])
            ti = idx.get(e["target"])
            if si is None or ti is None:
                continue
            ddx = nodes[si]["x"] - nodes[ti]["x"]
            ddy = nodes[si]["y"] - nodes[ti]["y"]
            dist = math.sqrt(ddx * ddx + ddy * ddy) + 0.01
            force = attraction * dist * e.get("weight", 1)
            fx = ddx / dist * force
            fy = ddy / dist * force
            dx_arr[si] -= fx
            dy_arr[si] -= fy
            dx_arr[ti] += fx
            dy_arr[ti] += fy

        for i in range(n):
            dx_arr[i] -= nodes[i]["x"] * gravity
            dy_arr[i] -= nodes[i]["y"] * gravity

        for i in range(n):
            disp = math.sqrt(dx_arr[i] ** 2 + dy_arr[i] ** 2) + 0.01
            scale = min(temp, disp) / disp
            nodes[i]["x"] += dx_arr[i] * scale
            nodes[i]["y"] += dy_arr[i] * scale

        temp *= cooling

    for node in nodes:
        node["x"] = round(node["x"], 2)
        node["y"] = round(node["y"], 2)


# --- Endpoints ---


@router.get("/cartographie/graph")
async def get_graph(
    db: AsyncSession = Depends(get_db),
    groupe_ref: str | None = Query(None, description="Filtrer par groupe politique"),
    theme: str | None = Query(None, description="Filtrer par theme"),
    min_weight: int = Query(2, ge=1, description="Poids minimum d'arete"),
    max_edges: int = Query(2000, ge=100, le=5000, description="Nombre max d'aretes"),
):
    """Graphe des relations entre deputes avec positions pre-calculees."""

    edge_map: dict[tuple[str, str], dict] = {}

    # A. Co-autorat de textes
    stmt_coauthor = (
        select(
            texte_auteurs.c.acteur_uid.label("a1"),
            texte_auteurs.c.acteur_uid.label("a2_placeholder"),
        )
    )
    # Use raw SQL for the self-join on texte_auteurs
    coauthor_sql = """
        SELECT ta1.acteur_uid AS source, ta2.acteur_uid AS target, COUNT(*) AS weight
        FROM texte_auteurs ta1
        JOIN texte_auteurs ta2 ON ta1.texte_uid = ta2.texte_uid AND ta1.acteur_uid < ta2.acteur_uid
        GROUP BY ta1.acteur_uid, ta2.acteur_uid
    """
    result = await db.execute(text(coauthor_sql))
    for row in result.all():
        key = (row[0], row[1])
        edge_map[key] = {"weight": row[2], "types": ["texte_coauthor"]}

    # B. Co-signataires
    cosig_sql = """
        SELECT am.auteur_ref AS source, ac.acteur_uid AS target, COUNT(*) AS weight
        FROM amendements am
        JOIN amendement_cosignataires ac ON am.uid = ac.amendement_uid
        WHERE am.auteur_ref IS NOT NULL AND am.auteur_ref < ac.acteur_uid
        GROUP BY am.auteur_ref, ac.acteur_uid
    """
    result = await db.execute(text(cosig_sql))
    for row in result.all():
        key = (row[0], row[1])
        if key not in edge_map:
            edge_map[key] = {"weight": 0, "types": []}
        edge_map[key]["weight"] += row[2]
        if "cosignataire" not in edge_map[key]["types"]:
            edge_map[key]["types"].append("cosignataire")

    # Filtrer et trier
    edges_raw = [
        {"source": k[0], "target": k[1], "weight": v["weight"], "types": v["types"]}
        for k, v in edge_map.items()
        if v["weight"] >= min_weight and k[0] and k[1]
    ]
    edges_raw.sort(key=lambda e: e["weight"], reverse=True)
    edges_raw = edges_raw[:max_edges]

    # Collecter les UIDs
    node_uids = set()
    for e in edges_raw:
        node_uids.add(e["source"])
        node_uids.add(e["target"])

    if not node_uids:
        return {"nodes": [], "edges": [], "meta": {"total_nodes": 0, "total_edges": 0}}

    # Filtrer par groupe si demande
    if groupe_ref:
        result = await db.execute(
            select(Acteur.uid).where(
                Acteur.uid.in_(node_uids),
                Acteur.groupe_politique_ref == groupe_ref,
            )
        )
        node_uids = {row[0] for row in result.all()}
        edges_raw = [
            e for e in edges_raw
            if e["source"] in node_uids and e["target"] in node_uids
        ]

    # Charger acteurs
    result = await db.execute(
        select(Acteur)
        .options(joinedload(Acteur.groupe_politique))
        .where(Acteur.uid.in_(node_uids))
    )
    acteurs = {a.uid: a for a in result.unique().scalars().all()}

    # Stats amendements par acteur
    result = await db.execute(
        select(Amendement.auteur_ref, func.count(Amendement.uid))
        .where(Amendement.auteur_ref.in_(node_uids))
        .group_by(Amendement.auteur_ref)
    )
    amdt_counts = dict(result.all())

    # Taux adoption par acteur
    adoption_stats = {}
    result = await db.execute(
        select(
            Amendement.auteur_ref,
            func.count(Amendement.uid),
            func.sum(func.iif(Amendement.sort.ilike("%adopt%"), 1, 0)),
        )
        .where(
            Amendement.auteur_ref.in_(node_uids),
            Amendement.sort.isnot(None),
        )
        .group_by(Amendement.auteur_ref)
    )
    for row in result.all():
        adopted = row[2] or 0
        adoption_stats[row[0]] = {
            "total_sorted": row[1],
            "nb_adopted": adopted,
            "adoption_rate": round(adopted / row[1], 3) if row[1] > 0 else 0,
        }

    # Construire noeuds
    nodes = []
    for uid in node_uids:
        a = acteurs.get(uid)
        if not a:
            continue
        gp = a.groupe_politique
        astats = adoption_stats.get(uid, {})
        nodes.append({
            "uid": a.uid,
            "label": f"{a.prenom or ''} {a.nom or ''}".strip(),
            "groupe_uid": a.groupe_politique_ref,
            "groupe_court": (gp.libelle_court if gp else None) or "",
            "groupe_label": (gp.libelle if gp else None) or "",
            "nb_amendements": amdt_counts.get(uid, 0),
            "adoption_rate": astats.get("adoption_rate", 0),
            "nb_adopted": astats.get("nb_adopted", 0),
            "x": 0.0,
            "y": 0.0,
        })

    valid_uids = {n["uid"] for n in nodes}
    edges_raw = [e for e in edges_raw if e["source"] in valid_uids and e["target"] in valid_uids]

    _force_layout(nodes, edges_raw)

    type_counts = defaultdict(int)
    for e in edges_raw:
        for t in e["types"]:
            type_counts[t] += 1

    return {
        "nodes": nodes,
        "edges": edges_raw,
        "meta": {
            "total_nodes": len(nodes),
            "total_edges": len(edges_raw),
            "edge_types": dict(type_counts),
        },
    }


@router.get("/cartographie/stats")
async def get_cartographie_stats(
    db: AsyncSession = Depends(get_db),
    groupe_ref: str | None = Query(None),
    theme: str | None = Query(None),
    min_weight: int = Query(2, ge=1),
    max_edges: int = Query(2000, ge=100, le=5000),
):
    """Statistiques analytiques du reseau parlementaire."""
    graph_data = await get_graph(
        db=db, groupe_ref=groupe_ref, theme=theme,
        min_weight=min_weight, max_edges=max_edges,
    )

    nodes = graph_data["nodes"]
    edges = graph_data["edges"]
    node_map = {n["uid"]: n for n in nodes}

    # Top deputies par connexions (degre)
    degree = defaultdict(int)
    for e in edges:
        degree[e["source"]] += 1
        degree[e["target"]] += 1

    top_deputies = []
    for uid, deg in sorted(degree.items(), key=lambda x: -x[1])[:15]:
        n = node_map.get(uid)
        if n:
            top_deputies.append({
                "uid": uid,
                "label": n["label"],
                "groupe_court": n["groupe_court"],
                "nb_connections": deg,
                "nb_amendements": n["nb_amendements"],
                "adoption_rate": n["adoption_rate"],
            })

    # Stats par groupe (liens internes vs externes)
    group_internal = defaultdict(int)
    group_external = defaultdict(int)
    group_deputes = defaultdict(set)

    for n in nodes:
        gc = n["groupe_court"]
        if gc:
            group_deputes[gc].add(n["uid"])

    for e in edges:
        src_grp = node_map.get(e["source"], {}).get("groupe_court", "")
        tgt_grp = node_map.get(e["target"], {}).get("groupe_court", "")
        if src_grp and src_grp == tgt_grp:
            group_internal[src_grp] += 1
        else:
            if src_grp:
                group_external[src_grp] += 1
            if tgt_grp:
                group_external[tgt_grp] += 1

    all_groups = set(group_internal.keys()) | set(group_external.keys())
    group_stats = sorted(
        [
            {
                "libelle_court": g,
                "nb_deputes_in_graph": len(group_deputes.get(g, set())),
                "nb_internal_edges": group_internal.get(g, 0),
                "nb_external_edges": group_external.get(g, 0),
            }
            for g in all_groups
        ],
        key=lambda x: -(x["nb_internal_edges"] + x["nb_external_edges"]),
    )

    return {
        "top_deputies": top_deputies,
        "group_stats": group_stats,
    }


@router.get("/cartographie/depute/{uid}")
async def get_depute_profile(
    uid: str,
    db: AsyncSession = Depends(get_db),
    period_days: int = Query(90, ge=1, le=1825, description="Periode d'analyse en jours"),
):
    """Profil d'influence d'un depute avec statistiques detaillees."""
    result = await db.execute(
        select(Acteur)
        .options(joinedload(Acteur.groupe_politique))
        .where(Acteur.uid == uid)
    )
    acteur = result.unique().scalars().first()
    if not acteur:
        raise HTTPException(status_code=404, detail="Depute non trouve")

    cutoff = datetime.utcnow() - timedelta(days=period_days)

    # Amendements sur la periode
    result = await db.execute(
        select(Amendement).where(
            Amendement.auteur_ref == uid,
            Amendement.date_depot >= cutoff,
        )
    )
    amdts_periode = result.scalars().all()
    nb_amdts = len(amdts_periode)

    # Amendements adoptes (toute la base)
    nb_adoptes = (await db.execute(
        select(func.count(Amendement.uid)).where(
            Amendement.auteur_ref == uid,
            Amendement.sort.ilike("%adopt%"),
        )
    )).scalar() or 0

    nb_total_sorted = (await db.execute(
        select(func.count(Amendement.uid)).where(
            Amendement.auteur_ref == uid,
            Amendement.sort.isnot(None),
        )
    )).scalar() or 0

    taux_adoption = round(nb_adoptes / nb_total_sorted, 3) if nb_total_sorted > 0 else 0

    # Textes (co)auteur
    nb_textes = (await db.execute(
        select(func.count(texte_auteurs.c.texte_uid)).where(
            texte_auteurs.c.acteur_uid == uid,
        )
    )).scalar() or 0

    # Cosignatures
    nb_cosignatures = (await db.execute(
        select(func.count(amendement_cosignataires.c.amendement_uid)).where(
            amendement_cosignataires.c.acteur_uid == uid,
        )
    )).scalar() or 0

    # Score d'influence composite (formule LegisAPI)
    score_influence = round(nb_amdts * 1 + nb_adoptes * 3 + nb_textes * 5 + nb_cosignatures * 0.5, 1)

    # Top 5 themes
    theme_counts: dict[str, int] = {}
    for a in amdts_periode:
        if a.themes:
            try:
                for t in json.loads(a.themes):
                    theme_counts[t] = theme_counts.get(t, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass
    top_themes = sorted(theme_counts.items(), key=lambda x: -x[1])[:5]

    gp = acteur.groupe_politique
    return {
        "uid": acteur.uid,
        "prenom": acteur.prenom,
        "nom": acteur.nom,
        "groupe": {
            "uid": gp.uid if gp else None,
            "libelle": gp.libelle if gp else None,
            "libelle_court": gp.libelle_court if gp else None,
        } if gp else None,
        "period_days": period_days,
        "activite": {
            "amdts_periode": nb_amdts,
            "textes": nb_textes,
            "cosignatures": nb_cosignatures,
        },
        "taux_adoption": taux_adoption,
        "nb_adoptes": nb_adoptes,
        "nb_total_sorted": nb_total_sorted,
        "score_influence": score_influence,
        "top_themes": [{"theme": t, "count": c} for t, c in top_themes],
    }


@router.get("/cartographie/groupes")
async def stats_par_groupe(db: AsyncSession = Depends(get_db)):
    """Nombre de deputes et d'amendements par groupe politique."""
    result = await db.execute(
        select(
            Organe.uid,
            Organe.libelle,
            Organe.libelle_court,
            func.count(Acteur.uid).label("nb_deputes"),
        )
        .join(Acteur, Acteur.groupe_politique_ref == Organe.uid)
        .where(Organe.type_code == "GP")
        .group_by(Organe.uid, Organe.libelle, Organe.libelle_court)
        .order_by(func.count(Acteur.uid).desc())
    )
    groups = result.all()

    output = []
    for g in groups:
        nb_amendements = (await db.execute(
            select(func.count(Amendement.uid)).where(Amendement.groupe_ref == g.uid)
        )).scalar() or 0

        # Taux adoption du groupe
        nb_sorted = (await db.execute(
            select(func.count(Amendement.uid)).where(
                Amendement.groupe_ref == g.uid,
                Amendement.sort.isnot(None),
            )
        )).scalar() or 0
        nb_adoptes = (await db.execute(
            select(func.count(Amendement.uid)).where(
                Amendement.groupe_ref == g.uid,
                Amendement.sort.ilike("%adopt%"),
            )
        )).scalar() or 0

        output.append({
            "uid": g.uid,
            "libelle": g.libelle,
            "libelle_court": g.libelle_court,
            "nb_deputes": g.nb_deputes,
            "nb_amendements": nb_amendements,
            "taux_adoption": round(nb_adoptes / nb_sorted, 3) if nb_sorted > 0 else 0,
        })

    return output


@router.get("/cartographie/secteur/{theme:path}")
async def get_secteur(
    theme: str,
    db: AsyncSession = Depends(get_db),
    days: int = Query(1825, ge=1, le=1825),
):
    """Intelligence sectorielle : textes, amendements, deputes cles par theme."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    theme_like = f'%"{theme}"%'

    # Textes du secteur
    result = await db.execute(
        select(Texte)
        .where(Texte.themes.ilike(theme_like), Texte.date_depot >= cutoff)
        .order_by(Texte.date_depot.desc())
        .limit(20)
    )
    textes = result.scalars().all()
    textes_out = [
        {
            "uid": t.uid,
            "titre": t.titre_court or t.titre or t.uid,
            "type_code": t.type_code,
            "date_depot": t.date_depot.isoformat() if t.date_depot else None,
            "themes": json.loads(t.themes) if t.themes else [],
            "resume_ia": t.resume_ia,
        }
        for t in textes
    ]

    # Amendements du secteur
    result = await db.execute(
        select(Amendement)
        .options(joinedload(Amendement.auteur), joinedload(Amendement.groupe))
        .where(Amendement.themes.ilike(theme_like), Amendement.date_depot >= cutoff)
        .order_by(Amendement.date_depot.desc())
    )
    all_amdts = result.unique().scalars().all()

    # Deputes cles (top 15 par activite dans le theme)
    depute_activity: dict[str, dict] = {}
    for a in all_amdts:
        if a.auteur_ref:
            if a.auteur_ref not in depute_activity:
                depute_activity[a.auteur_ref] = {"total": 0, "adoptes": 0}
            depute_activity[a.auteur_ref]["total"] += 1
            if a.sort and "adopt" in a.sort.lower():
                depute_activity[a.auteur_ref]["adoptes"] += 1

    top_depute_uids = sorted(
        depute_activity,
        key=lambda uid: depute_activity[uid]["total"],
        reverse=True,
    )[:15]

    deputes_cles = []
    if top_depute_uids:
        result = await db.execute(
            select(Acteur)
            .options(joinedload(Acteur.groupe_politique))
            .where(Acteur.uid.in_(top_depute_uids))
        )
        acteur_map = {a.uid: a for a in result.unique().scalars().all()}
        for uid in top_depute_uids:
            a = acteur_map.get(uid)
            if a:
                gp = a.groupe_politique
                stats = depute_activity[uid]
                taux = round(stats["adoptes"] / stats["total"], 3) if stats["total"] else 0
                deputes_cles.append({
                    "uid": a.uid,
                    "nom": f"{a.prenom or ''} {a.nom or ''}".strip(),
                    "groupe": (gp.libelle_court or gp.libelle) if gp else None,
                    "nb_amdts_secteur": stats["total"],
                    "nb_adoptes_secteur": stats["adoptes"],
                    "taux_adoption_secteur": taux,
                })

    # Reunions a venir
    now = datetime.utcnow()
    result = await db.execute(
        select(Reunion)
        .options(joinedload(Reunion.organe))
        .where(Reunion.themes.ilike(theme_like), Reunion.date_debut >= now)
        .order_by(Reunion.date_debut.asc())
        .limit(10)
    )
    reunions = result.unique().scalars().all()
    reunions_out = [
        {
            "uid": r.uid,
            "date_debut": r.date_debut.isoformat() if r.date_debut else None,
            "organe": (r.organe.libelle_court or r.organe.libelle) if r.organe else None,
            "lieu": r.lieu,
            "resume_ia": r.resume_ia,
        }
        for r in reunions
    ]

    # Stats globales
    nb_adoptes = sum(1 for a in all_amdts if a.sort and "adopt" in a.sort.lower())
    nb_sorted = sum(1 for a in all_amdts if a.sort)
    taux_adoption = round(nb_adoptes / nb_sorted, 3) if nb_sorted > 0 else 0

    return {
        "theme": theme,
        "period_days": days,
        "textes": textes_out,
        "deputes_cles": deputes_cles,
        "reunions": reunions_out,
        "stats": {
            "taux_adoption": taux_adoption,
            "nb_textes": len(textes_out),
            "nb_amendements": len(all_amdts),
            "nb_adoptes": nb_adoptes,
            "nb_reunions_avenir": len(reunions_out),
        },
    }
