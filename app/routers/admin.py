"""Admin API routes."""

from fastapi import APIRouter
import json
import os
from datetime import datetime
from fastapi import HTTPException, Request
from .. import db
from ..api_common import get_current_user
from ..schemas import DropdownItemIn, DropdownItemRenameIn, LocalCardSettingIn, OwnerIn, UserIn
from ..services import (
    BACKUPS,
    FIXED_OWNERS,
    _dirty,
    get_master_session_moment,
    set_master_session_moment,
)

router = APIRouter()

@router.get("/api/users")
def get_users():
    with db.tx() as c:
        return db.rows(c, "SELECT id, name, created_at FROM users ORDER BY name")

@router.post("/api/users")
def add_user(u: UserIn, request: Request):
    name = u.name.strip()
    if not name:
        raise HTTPException(400, "Le prénom/nom ne peut pas être vide")
    with db.tx() as c:
        try:
            cur = c.execute("INSERT INTO users(name) VALUES(?)", (name,))
            uid = cur.lastrowid
            db.log_audit(c, get_current_user(request), "INSERT", "user", uid, f"Création utilisateur « {name} »", snapshot_after={"id": uid, "name": name})
            return {"id": uid, "name": name}
        except Exception:
            raise HTTPException(400, "Cet utilisateur existe déjà")

@router.put("/api/users/{uid}")
def upd_user(uid: int, u: UserIn, request: Request):
    name = u.name.strip()
    if not name:
        raise HTTPException(400, "Le prénom/nom ne peut pas être vide")
    with db.tx() as c:
        old = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not old:
            raise HTTPException(404, "Utilisateur introuvable")
        c.execute("UPDATE users SET name=? WHERE id=?", (name, uid))
        db.log_audit(c, get_current_user(request), "UPDATE", "user", uid, f"Renommage utilisateur « {old['name']} » -> « {name} »",
                     snapshot_before=dict(old), snapshot_after={"id": uid, "name": name})
    return {"ok": True}

@router.delete("/api/users/{uid}")
def del_user(uid: int, request: Request):
    with db.tx() as c:
        old = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not old:
            raise HTTPException(404, "Utilisateur introuvable")
        c.execute("DELETE FROM users WHERE id=?", (uid,))
        db.log_audit(c, get_current_user(request), "DELETE", "user", uid, f"Suppression utilisateur « {old['name']} »", snapshot_before=dict(old))
    return {"ok": True}

@router.get("/api/audit")
def get_audit(limit: int = 150):
    with db.tx() as c:
        return db.rows(c, "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))

@router.post("/api/audit/{log_id}/undo")
def undo_audit(log_id: int, request: Request):
    """Annule atomiquement l'opération désignée par le log_id."""
    import json
    actor = get_current_user(request)
    with db.tx() as c:
        log = c.execute("SELECT * FROM audit_logs WHERE id=?", (log_id,)).fetchone()
        if not log:
            raise HTTPException(404, "Entrée de log introuvable")
        if log["undone"]:
            raise HTTPException(400, "Cette action a déjà été annulée")

        ttype = log["target_type"]
        act = log["action"]
        sb = json.loads(log["snapshot_before"]) if log["snapshot_before"] else None
        sa = json.loads(log["snapshot_after"]) if log["snapshot_after"] else None

        # Logique d'inversion atomique
        if ttype == "book":
            if act == "INSERT" and sa:
                c.execute("UPDATE books SET active=0 WHERE id=?", (sa.get("id"),))
            elif act == "UPDATE" and sb:
                c.execute("""UPDATE books SET code=?, title=?, series=?, volume=?, author=?, publisher=?,
                             category=?, type=?, location=?, price=?, min_stock=?, active=? WHERE id=?""",
                          (sb.get("code"), sb.get("title"), sb.get("series"), sb.get("volume"), sb.get("author"),
                           sb.get("publisher"), sb.get("category"), sb.get("type"), sb.get("location"),
                           sb.get("price", 0), sb.get("min_stock", 2), sb.get("active", 1), sb.get("id")))
            elif act == "DELETE" and sb:
                c.execute("UPDATE books SET active=1 WHERE id=?", (sb.get("id"),))

        elif ttype == "lot":
            if act == "INSERT" and sa:
                # Vérifier si déjà alloué
                rem = c.execute(f"SELECT ({db.LOT_REMAINING}) r, qty_in FROM lots l WHERE l.id=?", (sa.get("id"),)).fetchone()
                if rem and rem["r"] < rem["qty_in"]:
                    raise HTTPException(400, "Impossible d'annuler cette réception : des exemplaires de ce lot ont déjà été vendus")
                c.execute("DELETE FROM lots WHERE id=?", (sa.get("id"),))

        elif ttype == "adjustment":
            if act == "INSERT" and sa:
                c.execute("DELETE FROM adjustments WHERE id=?", (sa.get("id"),))

        elif ttype == "sale":
            if act == "INSERT" and sa:
                c.execute("DELETE FROM sales WHERE id=?", (sa.get("id"),))

        elif ttype == "reservation":
            if act == "INSERT" and sa:
                c.execute("DELETE FROM reservations WHERE id=?", (sa.get("id"),))
            elif act == "UPDATE" and sb:
                c.execute("UPDATE reservations SET name=?, phone=?, title=?, qty=?, status=?, note=? WHERE id=?",
                          (sb.get("name"), sb.get("phone"), sb.get("title"), sb.get("qty", 1), sb.get("status"), sb.get("note"), sb.get("id")))
            elif act == "DELETE" and sb:
                c.execute("INSERT INTO reservations(id, name, phone, title, qty, date, status, note) VALUES(?,?,?,?,?,?,?,?)",
                          (sb.get("id"), sb.get("name"), sb.get("phone"), sb.get("title"), sb.get("qty", 1), sb.get("date"), sb.get("status"), sb.get("note")))

        elif ttype == "cash_movement":
            if act == "INSERT" and sa:
                c.execute("DELETE FROM cash_movements WHERE id=?", (sa.get("id"),))
            elif act == "DELETE" and sb:
                c.execute("INSERT INTO cash_movements(id, date, user_name, type, channel, amount, note) VALUES(?,?,?,?,?,?,?)",
                          (sb.get("id"), sb.get("date"), sb.get("user_name"), sb.get("type"), sb.get("channel"), sb.get("amount"), sb.get("note")))

        elif ttype == "settlement":
            if act == "INSERT" and sa:
                c.execute("DELETE FROM settlements WHERE id=?", (sa.get("id"),))

        elif ttype == "setting":
            if act == "UPDATE" and sb:
                c.execute(
                    "INSERT OR REPLACE INTO app_settings(key, value) VALUES(?,?)",
                    (sb["key"], sb["value"]),
                )

        elif ttype == "option":
            if act == "INSERT" and sa:
                c.execute("DELETE FROM dropdown_options WHERE id=?", (sa.get("id"),))
            elif act == "DELETE" and sb:
                c.execute("INSERT OR IGNORE INTO dropdown_options(id, group_key, label) VALUES(?,?,?)",
                          (sb.get("id"), sb.get("group_key"), sb.get("label")))
        else:
            raise HTTPException(400, f"Annulation non supportée pour {ttype}:{act}")

        c.execute("UPDATE audit_logs SET undone=1, undone_at=?, undone_by=? WHERE id=?",
                  (datetime.now().isoformat(timespec='seconds'), actor, log_id))
        db.log_audit(c, actor, "UNDO", ttype, log["target_id"], f"Annulation de l'action #{log_id} ({log['summary']})")

    return {"ok": True}

@router.get("/api/options")
def get_options():
    with db.tx() as c:
        rows = db.rows(c, "SELECT id, group_key, label FROM dropdown_options ORDER BY group_key, label")
        db_authors = [r[0] for r in c.execute("SELECT DISTINCT author FROM books WHERE author IS NOT NULL AND TRIM(author) != '' ORDER BY author").fetchall()]
        local_owner_names = [
            r["name"] for r in db.rows(
                c, "SELECT name FROM owners WHERE LOWER(TRIM(kind))='locale' ORDER BY name"
            )
        ]
        res = {
            "category": [], "type": [], "payment": [], "publisher": [],
            "service_moment": [], "authors": db_authors,
            "local_card_enabled": db.get_setting(c, "local_card_enabled", "0") == "1",
            "local_owner_names": local_owner_names,
        }
        for r in rows:
            if r["group_key"] in res:
                res[r["group_key"]].append({"id": r["id"], "label": r["label"]})
        return res


@router.put("/api/settings/local-card")
def set_local_card_setting(setting: LocalCardSettingIn, request: Request):
    actor = get_current_user(request)
    value = "1" if setting.enabled else "0"
    with db.tx() as c:
        old_value = db.get_setting(c, "local_card_enabled", "0")
        c.execute(
            "INSERT OR REPLACE INTO app_settings(key, value) VALUES('local_card_enabled', ?)",
            (value,),
        )
        if old_value != value:
            db.log_audit(
                c, actor, "UPDATE", "setting", None,
                "Activation des paiements CB pour le stock local" if setting.enabled
                else "Désactivation des paiements CB pour le stock local",
                snapshot_before={"key": "local_card_enabled", "value": old_value},
                snapshot_after={"key": "local_card_enabled", "value": value},
            )
    return {"local_card_enabled": setting.enabled}


@router.post("/api/options")
def add_option(opt: DropdownItemIn, request: Request):
    lbl = opt.label.strip()
    if not lbl:
        raise HTTPException(400, "Le libellé ne peut pas être vide")
    with db.tx() as c:
        try:
            cur = c.execute("INSERT INTO dropdown_options(group_key, label) VALUES(?,?)", (opt.group_key, lbl))
            oid = cur.lastrowid
            db.log_audit(c, get_current_user(request), "INSERT", "option", oid, f"Ajout option {opt.group_key}: « {lbl} »", snapshot_after={"id": oid, "group_key": opt.group_key, "label": lbl})
            return {"id": oid, "label": lbl, "group_key": opt.group_key}
        except Exception:
            raise HTTPException(400, "Cette option existe déjà")

@router.get("/api/options/{opt_id}/impact")
def get_option_impact(opt_id: int):
    """Calcule le nombre d'éléments impactés par un renommage ou une fusion."""
    with db.tx() as c:
        opt = c.execute("SELECT * FROM dropdown_options WHERE id=?", (opt_id,)).fetchone()
        if not opt:
            raise HTTPException(404, "Option introuvable")

        gk = opt["group_key"]
        lbl = opt["label"]
        books_count = 0
        sales_count = 0

        if gk == "category":
            books_count = c.execute("SELECT COUNT(*) FROM books WHERE category=?", (lbl,)).fetchone()[0]
        elif gk == "type":
            books_count = c.execute("SELECT COUNT(*) FROM books WHERE type=?", (lbl,)).fetchone()[0]
        elif gk == "publisher":
            books_count = c.execute("SELECT COUNT(*) FROM books WHERE publisher=?", (lbl,)).fetchone()[0]
        elif gk == "payment":
            sales_count = c.execute("SELECT COUNT(*) FROM sales WHERE payment=?", (lbl,)).fetchone()[0]
        elif gk == "service_moment":
            sales_count = c.execute("SELECT COUNT(*) FROM sales WHERE service_moment=?", (lbl,)).fetchone()[0]

        return {
            "id": opt_id,
            "group_key": gk,
            "label": lbl,
            "books_count": books_count,
            "sales_count": sales_count,
            "total_impact": books_count + sales_count
        }

@router.put("/api/options/{opt_id}")
def rename_or_merge_option(opt_id: int, body: DropdownItemRenameIn, request: Request):
    """Renomme ou fusionne une option avec mise à jour en cascade des livres/ventes et backup automatique."""
    new_lbl = body.new_label.strip()
    if not new_lbl:
        raise HTTPException(400, "Le nouveau libellé ne peut pas être vide")

    user = get_current_user(request)

    # 1. Créer immédiatement un snapshot SQLite de sécurité automatique
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    auto_backup_path = os.path.join(BACKUPS, f"avant_renommage_option_{stamp}.db")
    db.safe_backup_db(auto_backup_path)

    with db.tx() as c:
        old = c.execute("SELECT * FROM dropdown_options WHERE id=?", (opt_id,)).fetchone()
        if not old:
            raise HTTPException(404, "Option introuvable")

        gk = old["group_key"]
        old_lbl = old["label"]

        if old_lbl == new_lbl:
            return {"ok": True, "message": "Aucun changement nécessaire", "updated_books": 0, "updated_sales": 0}

        # Vérifier si la nouvelle option existe déjà (cas d'une fusion)
        target_opt = c.execute("SELECT id FROM dropdown_options WHERE group_key=? AND label=?", (gk, new_lbl)).fetchone()
        is_merge = target_opt is not None

        updated_books = 0
        updated_sales = 0

        # Mise à jour en cascade dans les tables métier
        if body.cascade:
            if gk == "category":
                cur = c.execute("UPDATE books SET category=? WHERE category=?", (new_lbl, old_lbl))
                updated_books = cur.rowcount
            elif gk == "type":
                cur = c.execute("UPDATE books SET type=? WHERE type=?", (new_lbl, old_lbl))
                updated_books = cur.rowcount
            elif gk == "publisher":
                cur = c.execute("UPDATE books SET publisher=? WHERE publisher=?", (new_lbl, old_lbl))
                updated_books = cur.rowcount
            elif gk == "payment":
                cur = c.execute("UPDATE sales SET payment=? WHERE payment=?", (new_lbl, old_lbl))
                updated_sales = cur.rowcount
            elif gk == "service_moment":
                cur = c.execute("UPDATE sales SET service_moment=? WHERE service_moment=?", (new_lbl, old_lbl))
                updated_sales = cur.rowcount
                if get_master_session_moment() == old_lbl:
                    set_master_session_moment(new_lbl)

        # Mise à jour de la table dropdown_options
        if is_merge:
            # Fusion : on supprime l'ancienne option puisque la nouvelle existe déjà
            c.execute("DELETE FROM dropdown_options WHERE id=?", (opt_id,))
            final_id = target_opt["id"]
        else:
            # Renommage simple
            c.execute("UPDATE dropdown_options SET label=? WHERE id=?", (new_lbl, opt_id))
            final_id = opt_id

        # Audit
        action_desc = f"Fusion de {gk} « {old_lbl} » vers « {new_lbl} »" if is_merge else f"Renommage de {gk} « {old_lbl} » en « {new_lbl} »"
        details = f"{action_desc} ({updated_books} livres et {updated_sales} ventes mis à jour en cascade). Sauvegarde créée : {os.path.basename(auto_backup_path)}"
        db.log_audit(c, user, "UPDATE", "option", final_id, details,
                     snapshot_before={"id": opt_id, "group_key": gk, "label": old_lbl},
                     snapshot_after={"id": final_id, "group_key": gk, "label": new_lbl, "merged": is_merge})

    # Marquer dirty pour rafraîchir immédiatement le miroir Excel
    _dirty.set()

    return {
        "ok": True,
        "is_merge": is_merge,
        "old_label": old_lbl,
        "new_label": new_lbl,
        "updated_books": updated_books,
        "updated_sales": updated_sales,
        "backup_created": os.path.basename(auto_backup_path)
    }

@router.delete("/api/options/{opt_id}")
def delete_option(opt_id: int, request: Request):
    with db.tx() as c:
        old = c.execute("SELECT * FROM dropdown_options WHERE id=?", (opt_id,)).fetchone()
        if old:
            c.execute("DELETE FROM dropdown_options WHERE id=?", (opt_id,))
            db.log_audit(c, get_current_user(request), "DELETE", "option", opt_id, f"Suppression option {old['group_key']}: « {old['label']} »", snapshot_before=dict(old))
    _dirty.set()
    return {"ok": True}

@router.get("/api/owners")
def owners():
    with db.tx() as c:
        return db.rows(c, "SELECT * FROM owners ORDER BY priority,name")

@router.post("/api/owners")
def owner_add(o: OwnerIn):
    if o.name.strip().lower() in FIXED_OWNERS:
        raise HTTPException(400, f"Le nom « {o.name} » est réservé pour les origines fondamentales.")
    with db.tx() as c:
        c.execute("INSERT INTO owners(name,kind,reverse_pct,priority,color) VALUES(?,?,?,?,?)",
                  (o.name, o.kind, o.reverse_pct, o.priority, o.color))
    return {"ok": True}

@router.put("/api/owners/{oid}")
def owner_upd(oid: int, o: OwnerIn):
    with db.tx() as c:
        existing = c.execute("SELECT * FROM owners WHERE id=?", (oid,)).fetchone()
        if not existing:
            raise HTTPException(404, "Origine introuvable")
        if existing["name"].strip().lower() in FIXED_OWNERS:
            raise HTTPException(403, f"L'origine « {existing['name']} » est une origine système fixe non modifiable.")
        if o.name.strip().lower() in FIXED_OWNERS and o.name.strip().lower() != existing["name"].strip().lower():
            raise HTTPException(400, f"Le nom « {o.name} » est réservé.")
        c.execute("UPDATE owners SET name=?,kind=?,reverse_pct=?,priority=?,color=? WHERE id=?",
                  (o.name, o.kind, o.reverse_pct, o.priority, o.color, oid))
    return {"ok": True}

@router.delete("/api/owners/{oid}")
def owner_del(oid: int):
    with db.tx() as c:
        existing = c.execute("SELECT * FROM owners WHERE id=?", (oid,)).fetchone()
        if not existing:
            raise HTTPException(404, "Origine introuvable")
        if existing["name"].strip().lower() in FIXED_OWNERS:
            raise HTTPException(403, f"L'origine « {existing['name']} » est une origine système fixe et ne peut pas être supprimée.")
        used = c.execute("SELECT 1 FROM lots WHERE owner_id=? LIMIT 1", (oid,)).fetchone()
        if used:
            raise HTTPException(400, "Impossible de supprimer une origine associée à des lots de stock existants.")
        c.execute("DELETE FROM owners WHERE id=?", (oid,))
    return {"ok": True}

@router.get("/api/gdpr/info")
def gdpr_info():
    """Référentiel de conformité CNIL / RGPD (Règlement UE 2016/679)."""
    return {
        "status": "CONFORME",
        "framework": "RGPD UE 2016/679 & Loi Informatique et Libertés",
        "data_controller": "Librairi-E (Gestion locale privée)",
        "purposes": [
            {"id": "sales", "label": "Encaissement et justificatifs comptables", "basis": "Obligation légale (Code de commerce)", "retention": "10 ans"},
            {"id": "reservations", "label": "Réservations d'ouvrages à la demande", "basis": "Exécution d'une demande de service", "retention": "90 jours après service/annulation"},
            {"id": "audit", "label": "Journal de sécurité et intégrité", "basis": "Intérêt légitime de sécurité (ANSSI)", "retention": "1 an glissant"}
        ],
        "principles": {
            "minimization": "Les tickets de caisse ne comportent aucun nom client personnel.",
            "privacy_by_design": "Architecture 100% locale, zéro Cloud, zéro pistage tiers.",
            "right_to_erasure": "Anonymisation automatique et masquage dans les snapshots d'audit."
        }
    }

@router.post("/api/gdpr/cleanup")
def gdpr_cleanup(request: Request, days: int = 90):
    """RGPD Art. 5.1.e : Anonymise les coordonnées personnelles des réservations closes."""
    user = get_current_user(request)
    with db.tx(immediate=True) as c:
        count = db.clean_gdpr_reservations(c, days_retention=max(1, days))
        if count > 0:
            db.log_audit(c, user, "UPDATE", "gdpr", None,
                         f"Purge RGPD : anonymisation de {count} réservation(s) de plus de {days} jours")
    return {"ok": True, "anonymized": count, "retention_days": days}
