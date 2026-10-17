"""API FastAPI locale – Librairie."""
import io
import json
import os
import re
import secrets
import sys
import threading
import time
import shutil
import socket
import zipfile
from datetime import date, datetime, timedelta
from urllib.parse import unquote
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from . import db, excel_io, security

app = FastAPI(title="Librairie")
db.init()

STATIC = os.path.join(sys._MEIPASS, "app", "static") if getattr(sys, "frozen", False) \
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
MIRROR = os.path.join(db.DATA_DIR, "Bibliotheque_miroir.xlsx")
BACKUPS = os.path.join(db.DATA_DIR, "sauvegardes")
os.makedirs(BACKUPS, exist_ok=True)
_dirty = threading.Event()


def _mirror_loop():
    """Excel toujours à jour en arrière-plan + snapshots SQLite et Excel ultra-sécurisés via .tmp et renommage atomique."""
    last_day = None
    last_hourly_backup = 0
    while True:
        time.sleep(4)
        now = datetime.now()
        today = now.date().isoformat()
        is_dirty = _dirty.is_set()
        
        if is_dirty or last_day != today:
            _dirty.clear()
            try:
                # 1. Écriture atomique du miroir Excel
                excel_io.export_workbook(MIRROR)
                
                # 2. Sauvegarde SQLite atomique à chaud (anti-corruption même si coupure de courant pendant l'écriture)
                daily_db = os.path.join(BACKUPS, f"librairie_{today}.db")
                db.safe_backup_db(daily_db)
                
                # 3. Snapshot miroir journalier
                daily_xl = os.path.join(BACKUPS, f"Bibliotheque_{today}.xlsx")
                tmp_xl = daily_xl + ".tmp"
                shutil.copyfile(MIRROR, tmp_xl)
                os.replace(tmp_xl, daily_xl)
                
                # 4. Snapshots glissants récents (toutes les heures en cas d'activité)
                if time.time() - last_hourly_backup > 3600 or last_day != today:
                    stamp = now.strftime("%Y%m%d_%H%M")
                    db.safe_backup_db(os.path.join(BACKUPS, f"librairie_{stamp}.db"))
                    last_hourly_backup = time.time()

                last_day = today
            except Exception as e:
                print("Erreur boucle de sauvegarde résiliente:", e)


@app.on_event("startup")
def _start():
    threading.Thread(target=_mirror_loop, daemon=True).start()


@app.middleware("http")
async def mark_dirty(request: Request, call_next):
    resp = await call_next(request)
    if request.method != "GET" and resp.status_code < 400:
        _dirty.set()
    return resp


@app.exception_handler(ValueError)
async def _ve(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=400)


# Doit rester APRÈS les autres middlewares : le dernier enregistré est le plus externe (premier exécuté).
app.middleware("http")(security.security_gate)


# ---------- modèles ----------
class OwnerIn(BaseModel):
    name: str
    kind: str = "maison_mere"
    reverse_pct: float = 100
    priority: int = 1
    color: Optional[str] = "#6c8cff"


class BookIn(BaseModel):
    code: str
    title: str
    series: Optional[str] = None
    volume: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    category: Optional[str] = "Standard"
    type: Optional[str] = None
    location: Optional[str] = None
    price: float = 0
    min_stock: int = 2
    is_pack: int = 0


class PackItem(BaseModel):
    book_id: int
    qty: int = 1


DATE_PATTERN = r"^(\d{4}-\d{2}-\d{2})?$"   # vide accepté : le serveur retombe sur aujourd'hui


class LotIn(BaseModel):
    book_id: int
    owner_id: int
    qty_in: int = Field(ge=1, le=100000)
    date: Optional[str] = Field(None, pattern=DATE_PATTERN)
    unit_cost: Optional[float] = Field(None, ge=0, le=100000)
    reverse_pct: Optional[float] = Field(None, ge=0, le=100)
    note: Optional[str] = Field(None, max_length=300)


class AdjIn(BaseModel):
    delta: int = Field(ge=-100000, le=100000)
    reason: Optional[str] = Field("Ajustement", max_length=300)
    date: Optional[str] = Field(None, pattern=DATE_PATTERN)


class AllocIn(BaseModel):
    book_id: Optional[int] = None   # composant (packs) ; vide = le livre de la ligne
    lot_id: Optional[int] = None    # None = vente hors stock (explicite)
    qty: int = Field(ge=1, le=1000)


class LineIn(BaseModel):
    book_id: int
    qty: int = Field(1, ge=1, le=1000)
    unit_price: Optional[float] = Field(None, ge=0, le=100000)
    allocations: List[AllocIn] = Field(default_factory=list, max_length=50)


class PaymentPartIn(BaseModel):
    payment: str = Field(max_length=60)
    amount: float = Field(gt=0, le=100000)


class SaleIn(BaseModel):
    date: Optional[str] = Field(None, pattern=DATE_PATTERN)
    payment: Optional[str] = Field("Espèces", max_length=200)
    payments: Optional[List[PaymentPartIn]] = None
    note: Optional[str] = Field(None, max_length=300)
    customer_gender: Optional[str] = Field(None, max_length=20)
    customer_age_group: Optional[str] = Field(None, max_length=40)
    is_star: Optional[int] = 0
    service_moment: Optional[str] = Field(None, max_length=60)
    lines: List[LineIn] = Field(min_length=1, max_length=200)


class CashMovementIn(BaseModel):
    user_name: str = Field(max_length=60)
    type: Literal["DEPOSIT", "WITHDRAWAL"]
    channel: Literal["ESPECES", "WERO", "PAYPAL"]
    amount: float = Field(gt=0, lt=100000)
    date: Optional[str] = Field(None, pattern=DATE_PATTERN)
    note: Optional[str] = Field(None, max_length=300)


class SettleIn(BaseModel):
    owner_id: int
    amount: float = Field(gt=-1000000, lt=1000000)
    date: Optional[str] = Field(None, pattern=DATE_PATTERN)
    note: Optional[str] = Field(None, max_length=300)


class ResIn(BaseModel):
    name: Optional[str] = Field(None, max_length=120)
    phone: Optional[str] = Field(None, max_length=40)
    title: Optional[str] = Field(None, max_length=300)
    qty: int = Field(1, ge=1, le=1000)
    status: str = Field("En attente", max_length=40)
    note: Optional[str] = Field(None, max_length=300)


class DropdownItemIn(BaseModel):
    group_key: Literal["category", "type", "payment", "publisher"]
    label: str = Field(min_length=1, max_length=80)


class DropdownItemRenameIn(BaseModel):
    new_label: str = Field(min_length=1, max_length=80)
    cascade: bool = True  # Mettre à jour en cascade les livres et ventes existants


class UserIn(BaseModel):
    name: str = Field(max_length=60)


class PairIn(BaseModel):
    code: str = Field(min_length=8, max_length=64)
    name: Optional[str] = Field(None, max_length=60)


def get_current_user(request: Request) -> str:
    """Utilisateur transmis par X-User (encodé en URL côté client) ; nettoyé, borné, sinon 'Anonyme'."""
    raw = request.headers.get("X-User") or request.query_params.get("user") or ""
    u = re.sub(r"[\x00-\x1f\x7f<>]", "", unquote(raw)).strip()[:60]
    return u or "Anonyme"


def require_known_user(request: Request) -> str:
    """Pour un téléphone : l'identité déclarée doit correspondre à un profil existant."""
    u = get_current_user(request)
    if getattr(request.state, "role", "desk") == "mobile":
        with db.tx() as c:
            if not c.execute("SELECT 1 FROM users WHERE name=?", (u,)).fetchone():
                raise HTTPException(400, "Profil libraire inconnu : choisissez votre prénom dans la liste")
    return u


# ---------- utilisateurs (profils simples) ----------
@app.get("/api/users")
def get_users():
    with db.tx() as c:
        return db.rows(c, "SELECT id, name, created_at FROM users ORDER BY name")


@app.post("/api/users")
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


@app.put("/api/users/{uid}")
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


@app.delete("/api/users/{uid}")
def del_user(uid: int, request: Request):
    with db.tx() as c:
        old = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not old:
            raise HTTPException(404, "Utilisateur introuvable")
        c.execute("DELETE FROM users WHERE id=?", (uid,))
        db.log_audit(c, get_current_user(request), "DELETE", "user", uid, f"Suppression utilisateur « {old['name']} »", snapshot_before=dict(old))
    return {"ok": True}


# ---------- journal d'audit & annulation (undo) ----------
@app.get("/api/audit")
def get_audit(limit: int = 150):
    with db.tx() as c:
        return db.rows(c, "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,))


@app.post("/api/audit/{log_id}/undo")
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


# ---------- options paramétrables (dropdowns) ----------
@app.get("/api/options")
def get_options():
    with db.tx() as c:
        rows = db.rows(c, "SELECT id, group_key, label FROM dropdown_options ORDER BY group_key, label")
        res = {"category": [], "type": [], "payment": [], "publisher": []}
        for r in rows:
            if r["group_key"] in res:
                res[r["group_key"]].append({"id": r["id"], "label": r["label"]})
        return res


@app.post("/api/options")
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


@app.get("/api/options/{opt_id}/impact")
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

        return {
            "id": opt_id,
            "group_key": gk,
            "label": lbl,
            "books_count": books_count,
            "sales_count": sales_count,
            "total_impact": books_count + sales_count
        }


@app.put("/api/options/{opt_id}")
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


@app.delete("/api/options/{opt_id}")
def delete_option(opt_id: int, request: Request):
    with db.tx() as c:
        old = c.execute("SELECT * FROM dropdown_options WHERE id=?", (opt_id,)).fetchone()
        if old:
            c.execute("DELETE FROM dropdown_options WHERE id=?", (opt_id,))
            db.log_audit(c, get_current_user(request), "DELETE", "option", opt_id, f"Suppression option {old['group_key']}: « {old['label']} »", snapshot_before=dict(old))
    _dirty.set()
    return {"ok": True}


# ---------- propriétaires ----------
FIXED_OWNERS = {"cité royale", "icc rennes"}

@app.get("/api/owners")
def owners():
    with db.tx() as c:
        return db.rows(c, "SELECT * FROM owners ORDER BY priority,name")


@app.post("/api/owners")
def owner_add(o: OwnerIn):
    if o.name.strip().lower() in FIXED_OWNERS:
        raise HTTPException(400, f"Le nom « {o.name} » est réservé pour les origines fondamentales.")
    with db.tx() as c:
        c.execute("INSERT INTO owners(name,kind,reverse_pct,priority,color) VALUES(?,?,?,?,?)",
                  (o.name, o.kind, o.reverse_pct, o.priority, o.color))
    return {"ok": True}


@app.put("/api/owners/{oid}")
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


@app.delete("/api/owners/{oid}")
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


# ---------- livres ----------
def _books(c, where="1=1", args=()):
    bl = db.rows(c, f"""SELECT b.*, COALESCE((SELECT SUM({db.LOT_REMAINING}) FROM lots l WHERE l.book_id=b.id),0) stock
        FROM books b WHERE b.active=1 AND {where} ORDER BY b.is_pack DESC, b.series, b.title, b.volume""", args)
    byo, lots_by = {}, {}
    for r in db.rows(c, f"""SELECT l.id, l.book_id, l.date, o.name owner, o.color, ({db.LOT_REMAINING}) remaining
            FROM lots l JOIN owners o ON o.id=l.owner_id ORDER BY l.date, l.id"""):
        if r["remaining"] > 0:
            lots_by.setdefault(r["book_id"], []).append(r)
    for r in db.rows(c, f"""SELECT l.book_id, o.name, o.color, SUM({db.LOT_REMAINING}) rem FROM lots l
            JOIN owners o ON o.id=l.owner_id GROUP BY l.book_id, o.id"""):
        if r["rem"]:
            byo.setdefault(r["book_id"], []).append({"owner": r["name"], "color": r["color"], "qty": r["rem"]})
    packs_by_book = {}
    for r in db.rows(c, """
        SELECT pi.book_id, p.id pack_id, p.code pack_code, p.title pack_title, p.price pack_price,
               (SELECT SUM(bk.price * pi2.qty) FROM pack_items pi2 JOIN books bk ON bk.id = pi2.book_id WHERE pi2.pack_id = p.id) separate_price,
               (SELECT GROUP_CONCAT(bk2.title, ' + ') FROM pack_items pi3 JOIN books bk2 ON bk2.id = pi3.book_id WHERE pi3.pack_id = p.id AND bk2.id != pi.book_id) other_items
        FROM pack_items pi
        JOIN books p ON p.id = pi.pack_id
        WHERE p.active = 1
    """):
        saving = round(float(r["separate_price"] or 0) - float(r["pack_price"] or 0), 2)
        packs_by_book.setdefault(r["book_id"], []).append({
            "id": r["pack_id"],
            "code": r["pack_code"],
            "title": r["pack_title"],
            "price": r["pack_price"],
            "separate_price": r["separate_price"],
            "other_items": r["other_items"] or "",
            "saving": saving
        })

    for b in bl:
        b["by_owner"] = byo.get(b["id"], [])
        b["lots"] = lots_by.get(b["id"], [])
        if b["is_pack"]:
            b["stock"] = db.pack_stock(c, b["id"])
            b["items"] = db.rows(c, """SELECT pi.book_id,pi.qty,bk.title FROM pack_items pi
                JOIN books bk ON bk.id=pi.book_id WHERE pi.pack_id=?""", (b["id"],))
            for it in b["items"]:
                it["lots"] = lots_by.get(it["book_id"], [])
            b["suggested_packs"] = []
        else:
            s_packs = packs_by_book.get(b["id"], [])
            for sp in s_packs:
                sp["stock"] = db.pack_stock(c, sp["id"])
            b["suggested_packs"] = s_packs
    return bl


@app.get("/api/books")
def books():
    with db.tx() as c:
        return _books(c)


@app.post("/api/books")
def book_add(b: BookIn, request: Request):
    with db.tx() as c:
        try:
            cur = c.execute("""INSERT INTO books(code,title,series,volume,author,publisher,category,type,location,price,min_stock,is_pack)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (b.code, b.title, b.series, b.volume, b.author, b.publisher,
                                                     b.category, b.type, b.location, b.price, b.min_stock, b.is_pack))
            bid = cur.lastrowid
            db.log_audit(c, get_current_user(request), "INSERT", "book", bid, f"Création livre « {b.title} » ({b.code})", snapshot_after=b.dict() | {"id": bid})
            return {"id": bid}
        except Exception:
            raise HTTPException(400, "Ce code existe déjà")


@app.put("/api/books/{bid}")
def book_upd(bid: int, b: BookIn, request: Request):
    with db.tx() as c:
        old = c.execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone()
        if not old:
            raise HTTPException(404, "Livre introuvable")
        c.execute("""UPDATE books SET code=?,title=?,series=?,volume=?,author=?,publisher=?,category=?,type=?,
            location=?,price=?,min_stock=? WHERE id=?""", (b.code, b.title, b.series, b.volume, b.author,
                                                           b.publisher, b.category, b.type, b.location, b.price, b.min_stock, bid))
        db.log_audit(c, get_current_user(request), "UPDATE", "book", bid, f"Modification fiche « {b.title} »", snapshot_before=dict(old), snapshot_after=b.dict() | {"id": bid})
    return {"ok": True}


@app.delete("/api/books/{bid}")
def book_del(bid: int, request: Request):
    with db.tx() as c:
        old = c.execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone()
        if old:
            c.execute("UPDATE books SET active=0 WHERE id=?", (bid,))
            db.log_audit(c, get_current_user(request), "DELETE", "book", bid, f"Archivage livre « {old['title']} »", snapshot_before=dict(old))
    return {"ok": True}


@app.put("/api/books/{bid}/pack")
def pack_set(bid: int, items: List[PackItem], request: Request):
    with db.tx() as c:
        bk = c.execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone()
        old_items = db.rows(c, "SELECT book_id, qty FROM pack_items WHERE pack_id=?", (bid,))
        c.execute("DELETE FROM pack_items WHERE pack_id=?", (bid,))
        for i in items:
            c.execute("INSERT INTO pack_items(pack_id,book_id,qty) VALUES(?,?,?) ON CONFLICT(pack_id,book_id) DO UPDATE SET qty=qty+excluded.qty",
                      (bid, i.book_id, max(1, i.qty)))
        db.log_audit(c, get_current_user(request), "UPDATE", "pack", bid, f"Modification composition pack « {bk['title'] if bk else bid} »",
                     snapshot_before={"items": old_items}, snapshot_after={"items": [i.dict() for i in items]})
    return {"ok": True}


# ---------- lots (entrées de stock) ----------
@app.get("/api/books/{bid}/lots")
def lots(bid: int):
    with db.tx() as c:
        return db.rows(c, f"""SELECT l.*, o.name owner, o.color, o.reverse_pct o_pct, ({db.LOT_REMAINING}) remaining
            FROM lots l JOIN owners o ON o.id=l.owner_id WHERE l.book_id=? ORDER BY l.date DESC""", (bid,))


@app.get("/api/books/{bid}/stats")
def book_stats(bid: int):
    with db.tx() as c:
        b = c.execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone()
        if not b:
            raise HTTPException(404, "Livre introuvable")

        is_pack = bool(b["is_pack"])

        if is_pack:
            stock_row = c.execute("""
                SELECT MIN(sub.stock / pi.qty) AS pack_stock
                FROM pack_items pi
                JOIN (
                    SELECT l.book_id,
                           COALESCE(SUM(l.qty_in), 0) + COALESCE((SELECT SUM(delta) FROM adjustments WHERE lot_id = l.id), 0) - COALESCE((SELECT SUM(qty) FROM allocations WHERE lot_id = l.id), 0) AS stock
                    FROM lots l
                    GROUP BY l.book_id
                ) sub ON sub.book_id = pi.book_id
                WHERE pi.pack_id = ?
            """, (bid,)).fetchone()
            total_stock = max(0, int(stock_row["pack_stock"])) if stock_row and stock_row["pack_stock"] is not None else 0
            owners = []
        else:
            all_lots = db.rows(c, f"""
                SELECT l.id, l.date, o.name AS owner, o.color, ({db.LOT_REMAINING}) AS remaining
                FROM lots l
                JOIN owners o ON o.id = l.owner_id
                WHERE l.book_id = ?
                ORDER BY o.priority ASC, l.date ASC
            """, (bid,))
            lots = [l for l in all_lots if (l["remaining"] or 0) > 0]
            total_stock = sum(l["remaining"] for l in lots)
            owners = [{"name": l["owner"], "color": l["color"], "remaining": l["remaining"]} for l in lots]

        if is_pack:
            sales_rows = db.rows(c, """
                SELECT l.qty, l.unit_price, s.date, s.service_moment,
                       s.customer_gender, s.customer_age_group, COALESCE(s.is_star, 0) AS is_star,
                       0 AS via_pack
                FROM sale_lines l
                JOIN sales s ON s.id = l.sale_id
                WHERE l.book_id = ?
                ORDER BY s.date DESC, s.id DESC
            """, (bid,))
        else:
            direct_sales = db.rows(c, """
                SELECT l.qty, l.unit_price, s.date, s.service_moment,
                       s.customer_gender, s.customer_age_group, COALESCE(s.is_star, 0) AS is_star,
                       0 AS via_pack
                FROM sale_lines l
                JOIN sales s ON s.id = l.sale_id
                WHERE l.book_id = ?
                ORDER BY s.date DESC, s.id DESC
            """, (bid,))

            pack_allocs = db.rows(c, """
                SELECT a.qty, (a.revenue / a.qty) AS unit_price, a.date, s.service_moment,
                       s.customer_gender, s.customer_age_group, COALESCE(s.is_star, 0) AS is_star,
                       1 AS via_pack
                FROM allocations a
                JOIN sale_lines l ON l.id = a.line_id
                JOIN sales s ON s.id = l.sale_id
                WHERE a.book_id = ? AND l.book_id != ?
                ORDER BY a.date DESC, a.id DESC
            """, (bid, bid))

            sales_rows = sorted(direct_sales + pack_allocs, key=lambda r: (r["date"], r.get("id", 0)), reverse=True)

        total_sold = sum(r["qty"] for r in sales_rows)
        total_revenue = sum(r["qty"] * (r["unit_price"] or 0) for r in sales_rows)
        in_packs_sold = sum(r["qty"] for r in sales_rows if r.get("via_pack"))

        since_30d = (date.today() - timedelta(days=30)).isoformat()
        sold_last_30d = sum(r["qty"] for r in sales_rows if r["date"] >= since_30d)

        gender_counts = {"Femme": 0, "Homme": 0, "Couple": 0, "Autre": 0}
        age_counts = {"Enfant / Ado": 0, "18-29 ans": 0, "30-59 ans": 0, "60+ ans": 0}
        star_count = 0

        for r in sales_rows:
            q = r["qty"]
            g = (r["customer_gender"] or "").strip()
            if g in gender_counts:
                gender_counts[g] += q
            else:
                gender_counts["Autre"] += q

            a = (r["customer_age_group"] or "").strip()
            if a in age_counts:
                age_counts[a] += q

            if r["is_star"]:
                star_count += q

        recent_sales = sales_rows[:4]

        related_packs = db.rows(c, """
            SELECT p.id, p.title, p.price, pi.qty
            FROM pack_items pi
            JOIN books p ON p.id = pi.pack_id
            WHERE pi.book_id = ?
        """, (bid,)) if not is_pack else []

        return {
            "book": {
                "id": b["id"],
                "code": b["code"],
                "title": b["title"],
                "price": b["price"],
                "author": b["author"],
                "publisher": b["publisher"],
                "category": b["category"],
                "is_pack": is_pack,
                "stock": total_stock,
                "owners": owners
            },
            "kpis": {
                "total_sold": total_sold,
                "total_revenue": round(total_revenue, 2),
                "in_packs_count": in_packs_sold,
                "sold_last_30d": sold_last_30d,
                "last_sale_date": sales_rows[0]["date"] if sales_rows else None,
                "last_sale_moment": sales_rows[0]["service_moment"] if sales_rows else None
            },
            "demographics": {
                "gender": gender_counts,
                "age_groups": [{"label": k, "count": v} for k, v in age_counts.items()],
                "star": {
                    "count": star_count,
                    "total": total_sold,
                    "pct": round(star_count / total_sold * 100) if total_sold > 0 else 0
                }
            },
            "recent_sales": recent_sales,
            "packs": related_packs
        }


@app.post("/api/lots")
def lot_add(l: LotIn, request: Request):
    with db.tx() as c:
        cur = c.execute("INSERT INTO lots(book_id,owner_id,date,qty_in,unit_cost,reverse_pct,note) VALUES(?,?,?,?,?,?,?)",
                        (l.book_id, l.owner_id, l.date or date.today().isoformat(), l.qty_in, l.unit_cost, l.reverse_pct, l.note))
        lid = cur.lastrowid
        bk = c.execute("SELECT title FROM books WHERE id=?", (l.book_id,)).fetchone()
        ow = c.execute("SELECT name FROM owners WHERE id=?", (l.owner_id,)).fetchone()
        db.log_audit(c, get_current_user(request), "INSERT", "lot", lid,
                     f"Entrée stock : {l.qty_in}× « {bk['title'] if bk else l.book_id} » ({ow['name'] if ow else l.owner_id})",
                     snapshot_after=l.dict() | {"id": lid})
    return {"ok": True}


@app.post("/api/lots/{lid}/adjust")
def lot_adjust(lid: int, a: AdjIn, request: Request):
    with db.tx() as c:
        lot = c.execute("SELECT * FROM lots WHERE id=?", (lid,)).fetchone()
        bk = c.execute("SELECT title FROM books WHERE id=?", (lot['book_id'],)).fetchone() if lot else None
        cur = c.execute("INSERT INTO adjustments(lot_id,date,delta,reason) VALUES(?,?,?,?)",
                        (lid, a.date or date.today().isoformat(), a.delta, a.reason))
        jid = cur.lastrowid
        db.log_audit(c, get_current_user(request), "INSERT", "adjustment", jid,
                     f"Ajustement stock ({'+' if a.delta > 0 else ''}{a.delta}) « {bk['title'] if bk else ''} » : {a.reason}",
                     snapshot_after={"id": jid, "lot_id": lid, "delta": a.delta, "reason": a.reason})
    return {"ok": True}


# ---------- ventes ----------
@app.post("/api/sales")
def sale_add(s: SaleIn, request: Request):
    user = require_known_user(request)
    
    with db.tx() as c:
        payments_list = [p.dict() for p in s.payments] if s.payments else None
        sid, warns = db.create_sale(c, s.date, s.payment, s.note, [l.dict() for l in s.lines],
                                    manual=True, user_name=user,
                                    customer_gender=s.customer_gender,
                                    customer_age_group=s.customer_age_group,
                                    is_star=s.is_star or 0,
                                    service_moment=s.service_moment,
                                    payments=payments_list)
        total = sum((l.unit_price if l.unit_price is not None else
                     c.execute("SELECT price FROM books WHERE id=?", (l.book_id,)).fetchone()["price"]) * l.qty for l in s.lines)
        sale_row = c.execute("SELECT payment FROM sales WHERE id=?", (sid,)).fetchone()
        eff_payment = sale_row["payment"] if sale_row else s.payment
        db.log_audit(c, user, "INSERT", "sale", sid,
                     f"Vente #{sid} : {total:.2f} € ({len(s.lines)} article(s), {eff_payment}) par {user}",
                     snapshot_after={"id": sid, "date": s.date, "total": total, "payment": eff_payment,
                                     "payments": payments_list, "user_name": user,
                                     "customer_gender": s.customer_gender, "customer_age_group": s.customer_age_group,
                                     "is_star": s.is_star, "service_moment": s.service_moment, "lines": [l.dict() for l in s.lines]})
    return {"id": sid, "total": total, "warnings": warns}


@app.get("/api/sales")
def sales(limit: int = 200):
    with db.tx() as c:
        return db.rows(c, """SELECT s.id,s.date,s.payment,s.note,COALESCE(s.user_name,'Anonyme') user_name,
            s.customer_gender, s.customer_age_group, COALESCE(s.is_star, 0) is_star, s.service_moment,
            SUM(l.qty*l.unit_price) total, SUM(l.qty) qty,
            GROUP_CONCAT(l.qty||'× '||b.title, ' · ') detail
            FROM sales s JOIN sale_lines l ON l.sale_id=s.id JOIN books b ON b.id=l.book_id
            GROUP BY s.id ORDER BY s.date DESC, s.id DESC LIMIT ?""", (limit,))


@app.delete("/api/sales/{sid}")
def sale_del(sid: int, request: Request):
    with db.tx() as c:
        sale = c.execute("SELECT * FROM sales WHERE id=?", (sid,)).fetchone()
        if sale:
            sale_payments = db.rows(c, "SELECT payment, amount FROM sale_payments WHERE sale_id=?", (sid,))
            c.execute("DELETE FROM sales WHERE id=?", (sid,))
            db.log_audit(c, get_current_user(request), "DELETE", "sale", sid,
                         f"Suppression/annulation vente #{sid}",
                         snapshot_before=dict(sale) | {"payments": sale_payments})
    return {"ok": True}


# ---------- trésorerie & caisse ----------
@app.get("/api/treasury")
def treasury_summary():
    with db.tx() as c:
        # 1. Total par mode de paiement dans les ventes (calcul fin basé sur sale_payments)
        sales_by_pay = db.rows(c, """
            SELECT payment, COALESCE(SUM(amount), 0) total, COUNT(DISTINCT sale_id) count
            FROM sale_payments
            GROUP BY payment
        """)
        
        # 2. Total des mouvements de caisse enregistrés
        movements = db.rows(c, "SELECT * FROM cash_movements ORDER BY date DESC, id DESC")
        
        # 3. Calcul de la caisse physique locale (ICC Rennes)
        # RÈGLE MÉTIER : 100% de Cité Royale revient à Cité Royale et ne va JAMAIS dans la trésorerie / caisse locale.
        # Seules les ventes en espèces provenant d'exemplaires NON Cité Royale (ex: ICC Rennes) alimentent la caisse physique.
        sales_cash = c.execute("""
            SELECT COALESCE(SUM(sp.amount), 0) s
            FROM sale_payments sp
            JOIN sales s ON s.id = sp.sale_id
            WHERE sp.payment LIKE '%Espèce%'
              AND s.id IN (
                  SELECT l.sale_id FROM sale_lines l
                  JOIN allocations a ON a.line_id = l.id
                  JOIN owners o ON o.id = a.owner_id
                  WHERE LOWER(TRIM(o.name)) != 'cité royale'
              )
        """).fetchone()["s"]
        
        # Dépôts d'espèces régularisés en caisse par les libraires (pour la part ICC Rennes)
        deposits_cash = c.execute("""
            SELECT COALESCE(SUM(amount), 0) s FROM cash_movements WHERE type = 'DEPOSIT' AND channel = 'ESPECES'
        """).fetchone()["s"]
        
        # Sorties de caisse (remboursements aux libraires ou retraits)
        withdrawals_cash = c.execute("""
            SELECT COALESCE(SUM(amount), 0) s FROM cash_movements WHERE type = 'WITHDRAWAL' AND channel = 'ESPECES'
        """).fetchone()["s"]
        
        cash_in_drawer = sales_cash + deposits_cash - withdrawals_cash

        # Total Cité Royale payé directement sur CB / PayPal POS
        cr_paypal_total = c.execute("""
            SELECT COALESCE(SUM(sp.amount), 0) s
            FROM sale_payments sp
            JOIN sales s ON s.id = sp.sale_id
            WHERE (sp.payment = 'CB' OR sp.payment LIKE '%CB%' OR sp.payment LIKE '%PayPal%')
              AND s.id IN (
                  SELECT l.sale_id FROM sale_lines l
                  JOIN allocations a ON a.line_id = l.id
                  JOIN owners o ON o.id = a.owner_id
                  WHERE LOWER(TRIM(o.name)) = 'cité royale'
              )
        """).fetchone()["s"]

        # Total Cité Royale encaissé hors CB (que les libraires doivent passer sur CB / PayPal POS)
        cr_non_paypal_total = c.execute("""
            SELECT COALESCE(SUM(sp.amount), 0) s
            FROM sale_payments sp
            JOIN sales s ON s.id = sp.sale_id
            WHERE (sp.payment != 'CB' AND sp.payment NOT LIKE '%CB%' AND sp.payment NOT LIKE '%PayPal%')
              AND s.id IN (
                  SELECT l.sale_id FROM sale_lines l
                  JOIN allocations a ON a.line_id = l.id
                  JOIN owners o ON o.id = a.owner_id
                  WHERE LOWER(TRIM(o.name)) = 'cité royale'
              )
        """).fetchone()["s"]
        
        # 4. Solde & Dettes par utilisateur / libraire
        users = [u["name"] for u in db.rows(c, "SELECT name FROM users ORDER BY name")]
        extra_users = [r["u"] for r in db.rows(c, "SELECT DISTINCT user_name u FROM sales WHERE user_name IS NOT NULL AND user_name != '' UNION SELECT DISTINCT user_name u FROM cash_movements")]
        all_user_names = sorted(list(set(users + extra_users)))
        
        user_balances = []
        for uname in all_user_names:
            # Ventes totales encaissées par ce libraire pour Cité Royale hors CB / PayPal POS
            # (Le libraire doit payer lui-même ce montant sur la borne CB / PayPal POS pour régulariser Cité Royale)
            cr_due_to_paypal = c.execute("""
                SELECT COALESCE(SUM(sp.amount), 0) s
                FROM sale_payments sp
                JOIN sales s ON s.id = sp.sale_id
                WHERE s.user_name = ?
                  AND (sp.payment != 'CB' AND sp.payment NOT LIKE '%CB%' AND sp.payment NOT LIKE '%PayPal%')
                  AND s.id IN (
                      SELECT l.sale_id FROM sale_lines l
                      JOIN allocations a ON a.line_id = l.id
                      JOIN owners o ON o.id = a.owner_id
                      WHERE LOWER(TRIM(o.name)) = 'cité royale'
                  )
            """, (uname,)).fetchone()["s"]

            # Ventes ICC Rennes encaissées sur compte personnel (Wero / virement perso)
            # (Le libraire doit régulariser et déposer ce montant dans la caisse physique)
            icc_wero_received = c.execute("""
                SELECT COALESCE(SUM(sp.amount), 0) s
                FROM sale_payments sp
                JOIN sales s ON s.id = sp.sale_id
                WHERE s.user_name = ?
                  AND (sp.payment LIKE '%Wero%' OR sp.payment LIKE '%perso%')
                  AND s.id IN (
                      SELECT l.sale_id FROM sale_lines l
                      JOIN allocations a ON a.line_id = l.id
                      JOIN owners o ON o.id = a.owner_id
                      WHERE LOWER(TRIM(o.name)) != 'cité royale'
                  )
            """, (uname,)).fetchone()["s"]

            # Ventes totales tous canaux Wero (pour information)
            wero_received = c.execute("""
                SELECT COALESCE(SUM(sp.amount), 0) s
                FROM sale_payments sp
                JOIN sales s ON s.id = sp.sale_id
                WHERE s.user_name = ? AND (sp.payment LIKE '%Wero%' OR sp.payment LIKE '%perso%')
            """, (uname,)).fetchone()["s"]
            
            # Ventes où le libraire a encaissé des espèces (toutes origines)
            cash_received = c.execute("""
                SELECT COALESCE(SUM(sp.amount), 0) s
                FROM sale_payments sp
                JOIN sales s ON s.id = sp.sale_id
                WHERE s.user_name = ? AND sp.payment LIKE '%Espèce%'
            """, (uname,)).fetchone()["s"]
            
            # Ventes payées directement via CB / PayPal POS
            paypal_sales = c.execute("""
                SELECT COALESCE(SUM(sp.amount), 0) s
                FROM sale_payments sp
                JOIN sales s ON s.id = sp.sale_id
                WHERE s.user_name = ? AND (sp.payment = 'CB' OR sp.payment LIKE '%CB%' OR sp.payment LIKE '%PayPal%')
            """, (uname,)).fetchone()["s"]
            
            # Montant déjà déposé dans la caisse physique par ce libraire
            deposited = c.execute("""
                SELECT COALESCE(SUM(amount), 0) s
                FROM cash_movements
                WHERE user_name = ? AND type = 'DEPOSIT'
            """, (uname,)).fetchone()["s"]
            
            # Montant remboursé ou retiré par ce libraire depuis la caisse
            withdrawn = c.execute("""
                SELECT COALESCE(SUM(amount), 0) s
                FROM cash_movements
                WHERE user_name = ? AND type = 'WITHDRAWAL'
            """, (uname,)).fetchone()["s"]
            
            # Ce que le libraire doit déposer dans la caisse physique de l'église locale (ICC Rennes)
            net_to_deposit = icc_wero_received - deposited + withdrawn
            
            user_balances.append({
                "user_name": uname,
                "cr_due_to_paypal": cr_due_to_paypal,       # À régulariser sur PayPal POS (Cité Royale)
                "icc_wero_received": icc_wero_received,     # Wero ICC Rennes
                "wero_received": wero_received,
                "cash_received": cash_received,
                "paypal_sales": paypal_sales,
                "deposited": deposited,
                "withdrawn": withdrawn,
                "net_to_deposit": net_to_deposit            # À déposer dans le tiroir-caisse (ICC Rennes)
            })
            
        return {
            "cash_in_drawer": cash_in_drawer,
            "sales_cash": sales_cash,
            "deposits_cash": deposits_cash,
            "withdrawals_cash": withdrawals_cash,
            "cr_paypal_total": cr_paypal_total,
            "cr_non_paypal_total": cr_non_paypal_total,
            "sales_by_pay": sales_by_pay,
            "user_balances": user_balances,
            "movements": movements
        }


@app.post("/api/treasury/movements")
def cash_movement_add(m: CashMovementIn, request: Request):
    op_user = get_current_user(request)
    # Règle stricte d'intégrité : un libraire ne peut enregistrer un mouvement que pour lui-même
    if m.user_name and m.user_name != op_user:
        raise HTTPException(403, f"Opération refusée : vous êtes connecté en tant que « {op_user} » et ne pouvez pas enregistrer un mouvement pour « {m.user_name} »")
    
    m_user = op_user
    m_date = m.date or date.today().isoformat()
    with db.tx() as c:
        cur = c.execute("""
            INSERT INTO cash_movements(date, user_name, type, channel, amount, note)
            VALUES(?,?,?,?,?,?)
        """, (m_date, m_user, m.type, m.channel, m.amount, m.note))
        mid = cur.lastrowid
        desc = (f"Dépôt de {m.amount:.2f} € en caisse par {m_user} (régularisation Wero/espèces)"
                if m.type == 'DEPOSIT' else
                f"Retrait/Remboursement de {m.amount:.2f} € de la caisse pour {m_user}")
        db.log_audit(c, op_user, "INSERT", "cash_movement", mid, desc,
                     snapshot_after={"id": mid, "date": m_date, "user_name": m_user, "type": m.type, "channel": m.channel, "amount": m.amount, "note": m.note})
    return {"ok": True, "id": mid}


@app.delete("/api/treasury/movements/{mid}")
def cash_movement_del(mid: int, request: Request):
    op_user = get_current_user(request)
    with db.tx() as c:
        mov = c.execute("SELECT * FROM cash_movements WHERE id=?", (mid,)).fetchone()
        if not mov:
            raise HTTPException(404, "Mouvement introuvable")
        # Règle stricte : un libraire ne peut annuler/supprimer que ses propres mouvements
        if mov["user_name"] != op_user:
            raise HTTPException(403, f"Opération refusée : seul « {mov['user_name']} » peut modifier ou annuler ses propres opérations")
        c.execute("DELETE FROM cash_movements WHERE id=?", (mid,))
        db.log_audit(c, op_user, "DELETE", "cash_movement", mid,
                     f"Annulation mouvement caisse #{mid} ({mov['user_name']} - {mov['amount']:.2f} €)",
                     snapshot_before=dict(mov))
    return {"ok": True}


# ---------- reversements (archives / responsables) ----------
@app.get("/api/settlements")
def settlements():
    with db.tx() as c:
        out = []
        for o in db.rows(c, "SELECT * FROM owners ORDER BY priority"):
            a = c.execute("SELECT COALESCE(SUM(revenue),0) r,COALESCE(SUM(due),0) d,COALESCE(SUM(qty),0) q FROM allocations WHERE owner_id=?", (o["id"],)).fetchone()
            p = c.execute("SELECT COALESCE(SUM(amount),0) s FROM settlements WHERE owner_id=?", (o["id"],)).fetchone()["s"]
            o.update(revenue=a["r"], due=a["d"], qty=a["q"], paid=p, remaining=a["d"] - p, margin=a["r"] - a["d"],
                     history=db.rows(c, "SELECT * FROM settlements WHERE owner_id=? ORDER BY date DESC", (o["id"],)))
            out.append(o)
        return out


@app.post("/api/settlements")
def settle(s: SettleIn, request: Request):
    with db.tx() as c:
        cur = c.execute("INSERT INTO settlements(owner_id,date,amount,note) VALUES(?,?,?,?)",
                        (s.owner_id, s.date or date.today().isoformat(), s.amount, s.note))
        sid = cur.lastrowid
        ow = c.execute("SELECT name FROM owners WHERE id=?", (s.owner_id,)).fetchone()
        db.log_audit(c, get_current_user(request), "INSERT", "settlement", sid,
                     f"Règlement {s.amount:.2f} € à « {ow['name'] if ow else s.owner_id} »",
                     snapshot_after=s.dict() | {"id": sid})
    return {"ok": True}


# ---------- réservations ----------
@app.get("/api/reservations")
def res_list():
    with db.tx() as c:
        return db.rows(c, "SELECT * FROM reservations ORDER BY status='Servie', id DESC")


@app.post("/api/reservations")
def res_add(r: ResIn, request: Request):
    with db.tx() as c:
        cur = c.execute("INSERT INTO reservations(name,phone,title,qty,date,status,note) VALUES(?,?,?,?,?,?,?)",
                        (r.name, r.phone, r.title, r.qty, date.today().isoformat(), r.status, r.note))
        rid = cur.lastrowid
        db.log_audit(c, get_current_user(request), "INSERT", "reservation", rid,
                     f"Réservation pour « {r.name} » : {r.qty}× {r.title}", snapshot_after=r.dict() | {"id": rid})
    return {"ok": True}


@app.put("/api/reservations/{rid}")
def res_upd(rid: int, r: ResIn, request: Request):
    with db.tx() as c:
        old = c.execute("SELECT * FROM reservations WHERE id=?", (rid,)).fetchone()
        c.execute("UPDATE reservations SET name=?,phone=?,title=?,qty=?,status=?,note=? WHERE id=?",
                  (r.name, r.phone, r.title, r.qty, r.status, r.note, rid))
        db.log_audit(c, get_current_user(request), "UPDATE", "reservation", rid,
                     f"Mise à jour réservation #{rid} ({r.name}) -> statut: {r.status}",
                     snapshot_before=dict(old) if old else None, snapshot_after=r.dict() | {"id": rid})
    return {"ok": True}


@app.delete("/api/reservations/{rid}")
def res_del(rid: int, request: Request):
    with db.tx() as c:
        old = c.execute("SELECT * FROM reservations WHERE id=?", (rid,)).fetchone()
        if old:
            c.execute("DELETE FROM reservations WHERE id=?", (rid,))
            db.log_audit(c, get_current_user(request), "DELETE", "reservation", rid,
                         f"Suppression réservation #{rid} ({old['name']})", snapshot_before=dict(old))
    return {"ok": True}


# ---------- statistiques ----------
def _forecast(vals, n=3):
    k = len(vals)
    if k < 2:
        return [vals[-1] if vals else 0] * n
    xs = list(range(k))
    mx, my = sum(xs) / k, sum(vals) / k
    den = sum((x - mx) ** 2 for x in xs) or 1
    a = sum((x - mx) * (y - my) for x, y in zip(xs, vals)) / den
    b = my - a * mx
    return [max(0, a * (k + i) + b) for i in range(n)]


@app.get("/api/stats")
def stats(start: Optional[str] = None, end: Optional[str] = None, moment: Optional[str] = None):
    start = start or "0000-00-00"
    end = end or "9999-12-31"
    with db.tx() as c:
        W = "a.date BETWEEN ? AND ?"
        A = [start, end]
        Ws = "s.date BETWEEN ? AND ?"
        As = [start, end]

        if moment:
            W += " AND EXISTS (SELECT 1 FROM sale_lines sl JOIN sales s ON s.id = sl.sale_id WHERE sl.id = a.line_id AND s.service_moment = ?)"
            A.append(moment)
            Ws += " AND s.service_moment = ?"
            As.append(moment)

        A = tuple(A)
        As = tuple(As)

        k = c.execute(f"SELECT COALESCE(SUM(revenue),0) rev,COALESCE(SUM(due),0) due,COALESCE(SUM(qty),0) qty FROM allocations a WHERE {W}", A).fetchone()
        nb = c.execute(f"SELECT COUNT(*) n FROM sales s WHERE {Ws}", As).fetchone()["n"]
        sv = c.execute(f"""SELECT COALESCE(SUM(({db.LOT_REMAINING})*b.price),0) v, COALESCE(SUM({db.LOT_REMAINING}),0) u
            FROM lots l JOIN books b ON b.id=l.book_id""").fetchone()
        due_open = 0
        for o in db.rows(c, "SELECT id FROM owners"):
            d = c.execute("SELECT COALESCE(SUM(due),0) s FROM allocations WHERE owner_id=?", (o["id"],)).fetchone()["s"]
            p = c.execute("SELECT COALESCE(SUM(amount),0) s FROM settlements WHERE owner_id=?", (o["id"],)).fetchone()["s"]
            due_open += d - p
        monthly = db.rows(c, f"""SELECT strftime('%Y-%m',a.date) m, SUM(revenue) revenue, SUM(due) due, SUM(qty) qty
            FROM allocations a WHERE {W} GROUP BY m ORDER BY m""", A)
        by_owner_month = db.rows(c, f"""SELECT strftime('%Y-%m',a.date) m, COALESCE(o.name,'Sans stock') owner, COALESCE(o.color,'#8892b0') color, SUM(revenue) revenue
            FROM allocations a LEFT JOIN owners o ON o.id=a.owner_id WHERE {W} GROUP BY m,owner ORDER BY m""", A)
        fc_vals = [m["revenue"] for m in monthly][-6:]
        fc = _forecast(fc_vals)
        daily = db.rows(c, f"SELECT a.date d, SUM(revenue) revenue, SUM(qty) qty FROM allocations a WHERE {W} GROUP BY d ORDER BY d", A)
        top = db.rows(c, f"""SELECT b.title, b.code, SUM(a.qty) qty, SUM(a.revenue) revenue FROM allocations a
            JOIN books b ON b.id=a.book_id WHERE {W} GROUP BY b.id ORDER BY qty DESC, revenue DESC LIMIT 10""", A)
        by_cat = db.rows(c, f"""SELECT COALESCE(b.category,'?') label, SUM(a.revenue) revenue, SUM(a.qty) qty FROM allocations a
            JOIN books b ON b.id=a.book_id WHERE {W} GROUP BY label ORDER BY revenue DESC""", A)
        by_pub = db.rows(c, f"""SELECT COALESCE(b.publisher,'Non renseigné') label, SUM(a.revenue) revenue, SUM(a.qty) qty FROM allocations a
            JOIN books b ON b.id=a.book_id WHERE {W} GROUP BY label ORDER BY revenue DESC""", A)
        by_owner = db.rows(c, f"""SELECT COALESCE(o.name,'Sans stock') label, COALESCE(o.color,'#8892b0') color,
            SUM(a.revenue) revenue, SUM(a.due) due, SUM(a.qty) qty FROM allocations a
            LEFT JOIN owners o ON o.id=a.owner_id WHERE {W} GROUP BY label ORDER BY revenue DESC""", A)
        
        # Moyens de paiement avec chiffre d'affaires et volume
        pay = db.rows(c, f"""
            SELECT COALESCE(sp.payment, 'Non renseigné') label,
                   COUNT(DISTINCT sp.sale_id) n,
                   COALESCE(SUM(sp.amount), 0) revenue
            FROM sale_payments sp
            JOIN sales s ON s.id = sp.sale_id
            WHERE {Ws}
            GROUP BY label ORDER BY revenue DESC
        """, As)
        for p in pay:
            p["avg_basket"] = (p["revenue"] / p["n"]) if p["n"] else 0

        wd = db.rows(c, f"""SELECT CAST(strftime('%w',a.date) AS INT) d, SUM(revenue) revenue FROM allocations a WHERE {W} GROUP BY d""", A)
        low = [b for b in _books(c, "is_pack=0") if b["stock"] <= b["min_stock"]]
        low.sort(key=lambda b: b["stock"])
        # rotation : jours de stock restants (rythme des 30 derniers jours)
        since = (date.today() - timedelta(days=30)).isoformat()
        rate = {r["book_id"]: r["q"] / 30 for r in db.rows(c, "SELECT book_id, SUM(qty) q FROM allocations WHERE date>=? GROUP BY book_id", (since,))}
        for b in low:
            b["days_left"] = round(b["stock"] / rate[b["id"]]) if rate.get(b["id"]) else None
        
        # Ventes réelles de caisse (hors regroupement journalier Import Excel)
        pos_sales = c.execute(f"""
            SELECT COUNT(DISTINCT s.id) n, COALESCE(SUM(l.qty * l.unit_price), 0) rev
            FROM sales s
            JOIN sale_lines l ON l.sale_id = s.id
            WHERE {Ws} AND (s.note IS NULL OR s.note != 'Import Excel')
        """, As).fetchone()
        pos_nb = pos_sales["n"]
        pos_rev = pos_sales["rev"]
        pos_avg_basket = (pos_rev / pos_nb) if pos_nb else 0
        avg_book_price = (k["rev"] / k["qty"]) if k["qty"] else 0

        # Répartition démographique anonyme (Ventes caisse qualifiées)
        by_gender = db.rows(c, f"""
            SELECT COALESCE(customer_gender, 'Non renseigné') label,
                   COUNT(DISTINCT s.id) n,
                   COALESCE(SUM(l.qty * l.unit_price), 0) revenue,
                   COALESCE(SUM(l.qty), 0) qty
            FROM sales s
            JOIN sale_lines l ON l.sale_id = s.id
            WHERE {Ws} AND (s.note IS NULL OR s.note != 'Import Excel')
            GROUP BY label ORDER BY revenue DESC
        """, As)
        for g in by_gender:
            g["avg_basket"] = (g["revenue"] / g["n"]) if g["n"] else 0

        by_age = db.rows(c, f"""
            SELECT COALESCE(customer_age_group, 'Non renseigné') label,
                   COUNT(DISTINCT s.id) n,
                   COALESCE(SUM(l.qty * l.unit_price), 0) revenue,
                   COALESCE(SUM(l.qty), 0) qty
            FROM sales s
            JOIN sale_lines l ON l.sale_id = s.id
            WHERE {Ws} AND (s.note IS NULL OR s.note != 'Import Excel')
            GROUP BY label ORDER BY revenue DESC
        """, As)
        for a in by_age:
            a["avg_basket"] = (a["revenue"] / a["n"]) if a["n"] else 0

        by_star = db.rows(c, f"""
            SELECT CASE WHEN s.is_star = 1 THEN 'Serviteurs STAR ⭐' ELSE 'Autres fidèles & Visiteurs' END label,
                   s.is_star,
                   COUNT(DISTINCT s.id) n,
                   COALESCE(SUM(l.qty * l.unit_price), 0) revenue,
                   COALESCE(SUM(l.qty), 0) qty
            FROM sales s
            JOIN sale_lines l ON l.sale_id = s.id
            WHERE {Ws} AND (s.note IS NULL OR s.note != 'Import Excel')
            GROUP BY (s.is_star = 1) ORDER BY (s.is_star = 1) DESC
        """, As)
        for st_row in by_star:
            st_row["avg_basket"] = (st_row["revenue"] / st_row["n"]) if st_row["n"] else 0

        # Cultes & Temps de vente (enrichis avec panier moyen et best-seller)
        by_moment = db.rows(c, f"""
            SELECT COALESCE(s.service_moment, 'Non précisé') label,
                   COUNT(DISTINCT s.id) n,
                   COALESCE(SUM(l.qty * l.unit_price), 0) revenue,
                   COALESCE(SUM(l.qty), 0) qty
            FROM sales s
            JOIN sale_lines l ON l.sale_id = s.id
            WHERE s.date BETWEEN ? AND ? AND (s.note IS NULL OR s.note != 'Import Excel')
            GROUP BY label ORDER BY revenue DESC
        """, (start, end))
        for m in by_moment:
            m["avg_basket"] = (m["revenue"] / m["n"]) if m["n"] else 0
            top_bk = c.execute("""
                SELECT b.title, SUM(l.qty) q
                FROM sales s
                JOIN sale_lines l ON l.sale_id = s.id
                JOIN books b ON b.id = l.book_id
                WHERE s.date BETWEEN ? AND ? AND (s.note IS NULL OR s.note != 'Import Excel') AND COALESCE(s.service_moment, 'Non précisé') = ?
                GROUP BY b.id ORDER BY q DESC LIMIT 1
            """, (start, end, m["label"])).fetchone()
            m["top_book"] = top_bk["title"] if top_bk else None
            m["top_book_qty"] = top_bk["q"] if top_bk else 0

        return {"kpi": {"revenue": k["rev"], "due": k["due"], "margin": k["rev"] - k["due"], "qty": k["qty"],
                        "sales": nb, "pos_sales": pos_nb, "pos_avg_basket": pos_avg_basket,
                        "avg_book_price": avg_book_price,
                        "avg_basket": (k["rev"] / nb) if nb else 0,
                        "stock_value": sv["v"], "stock_units": sv["u"], "due_open": due_open},
                "monthly": monthly, "by_owner_month": by_owner_month, "forecast": fc,
                "daily": daily, "top": top, "by_category": by_cat, "by_publisher": by_pub, "by_owner": by_owner,
                "payments": pay, "weekday": wd, "by_gender": by_gender, "by_age": by_age, "by_star": by_star, "by_moment": by_moment, "low_stock": low[:30]}


# ---------- Studio d'Analyses Croisées & Métriques Personnalisables ----------
MATRIX_DIMENSIONS = {
    "moment": {
        "label": "Culte / Temps de vente",
        "expr": "COALESCE(s.service_moment, CASE WHEN s.note = 'Import Excel' THEN 'Import historique' ELSE 'Non précisé' END)",
    },
    "age": {
        "label": "Tranche d'Âge",
        "expr": "COALESCE(s.customer_age_group, CASE WHEN s.note = 'Import Excel' THEN 'Import historique' ELSE 'Non renseigné' END)",
    },
    "gender": {
        "label": "Genre",
        "expr": "COALESCE(s.customer_gender, CASE WHEN s.note = 'Import Excel' THEN 'Import historique' ELSE 'Non renseigné' END)",
    },
    "star": {
        "label": "Serviteur STAR",
        "expr": "CASE WHEN s.is_star = 1 THEN 'Serviteurs STAR ⭐' ELSE 'Autres fidèles & Visiteurs' END",
    },
    "category": {
        "label": "Catégorie / Rayon",
        "expr": "COALESCE(b.category, 'Non catégorisé')",
    },
    "publisher": {
        "label": "Éditeur",
        "expr": "COALESCE(b.publisher, 'Non renseigné')",
    },
    "payment": {
        "label": "Mode de Paiement",
        "expr": "COALESCE(s.payment, 'Non renseigné')",
    },
    "owner": {
        "label": "Origine du Stock",
        "expr": "COALESCE(o.name, 'Sans stock')",
    },
    "weekday": {
        "label": "Jour de la Semaine",
        "expr": "CASE CAST(strftime('%w', s.date) AS INT) WHEN 0 THEN '0. Dimanche' WHEN 1 THEN '1. Lundi' WHEN 2 THEN '2. Mardi' WHEN 3 THEN '3. Mercredi' WHEN 4 THEN '4. Jeudi' WHEN 5 THEN '5. Vendredi' WHEN 6 THEN '6. Samedi' END",
    },
    "month": {
        "label": "Mois de Vente",
        "expr": "strftime('%Y-%m', s.date)",
    }
}
MATRIX_ALIASES = {
    "service_moment": "moment",
    "customer_age_group": "age",
    "age_group": "age",
    "customer_gender": "gender",
    "is_star": "star",
}


@app.get("/api/stats/matrix")
def stats_matrix(
    start: Optional[str] = None,
    end: Optional[str] = None,
    row: str = "moment",
    col: Optional[str] = None,
    moment: Optional[str] = None,
    age_group: Optional[str] = None,
    gender: Optional[str] = None,
    is_star: Optional[str] = None,
    payment: Optional[str] = None,
    category: Optional[str] = None
):
    # Résolution des alias et validation stricte (sécurité SQL)
    row_key = MATRIX_ALIASES.get(row, row)
    if row_key not in MATRIX_DIMENSIONS:
        row_key = "moment"

    col_key = MATRIX_ALIASES.get(col, col) if col else None
    if col_key and (col_key not in MATRIX_DIMENSIONS or col_key == row_key):
        col_key = None

    row_cfg = MATRIX_DIMENSIONS[row_key]
    col_cfg = MATRIX_DIMENSIONS[col_key] if col_key else None

    row_expr = row_cfg["expr"]
    col_expr = col_cfg["expr"] if col_cfg else None

    where_parts = ["s.date BETWEEN ? AND ?"]
    where_args = [start or "0000-00-00", end or "9999-12-31"]

    if moment:
        where_parts.append("s.service_moment = ?")
        where_args.append(moment)
    if age_group:
        where_parts.append("s.customer_age_group = ?")
        where_args.append(age_group)
    if gender:
        where_parts.append("s.customer_gender = ?")
        where_args.append(gender)
    if is_star is not None and str(is_star).strip() != "":
        where_parts.append("s.is_star = ?")
        where_args.append(int(is_star))
    if payment:
        where_parts.append("s.payment = ?")
        where_args.append(payment)
    if category:
        where_parts.append("b.category = ?")
        where_args.append(category)

    where_sql = " AND ".join(where_parts)
    params = tuple(where_args)

    from_sql = """
        FROM allocations a
        JOIN sale_lines sl ON sl.id = a.line_id
        JOIN sales s ON s.id = sl.sale_id
        JOIN books b ON b.id = a.book_id
        LEFT JOIN owners o ON o.id = a.owner_id
    """

    with db.tx() as c:
        # 1. Totaux globaux sur le périmètre sélectionné
        q_tot = f"""
            SELECT 
                COALESCE(SUM(a.revenue), 0) total_revenue,
                COALESCE(SUM(a.due), 0) total_due,
                COALESCE(SUM(a.revenue - a.due), 0) total_margin,
                COALESCE(SUM(a.qty), 0) total_qty,
                COUNT(DISTINCT s.id) total_tickets,
                COUNT(DISTINCT CASE WHEN s.is_star = 1 THEN s.id END) total_star_tickets,
                COALESCE(SUM(CASE WHEN s.is_star = 1 THEN a.revenue ELSE 0 END), 0) total_star_revenue
            {from_sql}
            WHERE {where_sql}
        """
        tot = c.execute(q_tot, params).fetchone()
        tot_rev = tot["total_revenue"]
        tot_margin = tot["total_margin"]
        tot_qty = tot["total_qty"]
        tot_tickets = tot["total_tickets"]
        tot_star_rev = tot["total_star_revenue"]

        # 2. Agrégation principale
        if not col_key:
            q_agg = f"""
                SELECT 
                    {row_expr} as row_val,
                    COUNT(DISTINCT s.id) as tickets,
                    COALESCE(SUM(a.revenue), 0) as revenue,
                    COALESCE(SUM(a.due), 0) as due,
                    COALESCE(SUM(a.revenue - a.due), 0) as margin,
                    COALESCE(SUM(a.qty), 0) as qty,
                    COUNT(DISTINCT CASE WHEN s.is_star = 1 THEN s.id END) as star_tickets,
                    COALESCE(SUM(CASE WHEN s.is_star = 1 THEN a.revenue ELSE 0 END), 0) as star_revenue
                {from_sql}
                WHERE {where_sql}
                GROUP BY row_val
                ORDER BY revenue DESC
            """
            raw_rows = [dict(r) for r in c.execute(q_agg, params).fetchall()]

            # Top livre par ligne
            q_top = f"""
                WITH book_sales AS (
                    SELECT 
                        {row_expr} as row_val,
                        b.title,
                        SUM(a.qty) as book_qty,
                        SUM(a.revenue) as book_rev,
                        ROW_NUMBER() OVER (PARTITION BY {row_expr} ORDER BY SUM(a.qty) DESC, SUM(a.revenue) DESC) as rn
                    {from_sql}
                    WHERE {where_sql}
                    GROUP BY row_val, b.id
                )
                SELECT row_val, title, book_qty, book_rev FROM book_sales WHERE rn = 1
            """
            top_map = {r["row_val"]: r for r in c.execute(q_top, params).fetchall()}

            rows_out = []
            distinct_rows = set()
            for r in raw_rows:
                rv = r["row_val"]
                distinct_rows.add(rv)
                rev = r["revenue"]
                tix = r["tickets"]
                q = r["qty"]
                mrg = r["margin"]
                star_r = r["star_revenue"]
                tb = top_map.get(rv)

                rows_out.append({
                    "row_val": rv,
                    "revenue": round(rev, 2),
                    "due": round(r["due"], 2),
                    "margin": round(mrg, 2),
                    "qty": q,
                    "tickets": tix,
                    "avg_basket": round(rev / tix, 2) if tix else 0,
                    "avg_items_per_basket": round(q / tix, 2) if tix else 0,
                    "pct_revenue": round((rev / tot_rev * 100), 1) if tot_rev else 0,
                    "pct_margin": round((mrg / rev * 100), 1) if rev else 0,
                    "star_tickets": r["star_tickets"],
                    "star_revenue": round(star_r, 2),
                    "star_pct": round((star_r / rev * 100), 1) if rev else 0,
                    "top_book": tb["title"] if tb else None,
                    "top_book_qty": tb["book_qty"] if tb else 0,
                    "top_book_rev": round(tb["book_rev"], 2) if tb else 0
                })

            return {
                "total": {
                    "revenue": round(tot_rev, 2),
                    "due": round(tot["total_due"], 2),
                    "margin": round(tot_margin, 2),
                    "qty": tot_qty,
                    "tickets": tot_tickets,
                    "avg_basket": round(tot_rev / tot_tickets, 2) if tot_tickets else 0,
                    "avg_items_per_basket": round(tot_qty / tot_tickets, 2) if tot_tickets else 0,
                    "star_tickets": tot["total_star_tickets"],
                    "star_revenue": round(tot_star_rev, 2),
                    "star_pct": round(tot_star_rev / tot_rev * 100, 1) if tot_rev else 0,
                    "margin_pct": round(tot_margin / tot_rev * 100, 1) if tot_rev else 0,
                },
                "rows": rows_out,
                "dimension_row": row_key,
                "dimension_row_label": row_cfg["label"],
                "dimension_col": None,
                "dimension_col_label": None,
                "distinct_rows": sorted(list(distinct_rows)),
                "distinct_cols": []
            }

        else:
            # Croisement à deux dimensions
            q_agg = f"""
                SELECT 
                    {row_expr} as row_val,
                    {col_expr} as col_val,
                    COUNT(DISTINCT s.id) as tickets,
                    COALESCE(SUM(a.revenue), 0) as revenue,
                    COALESCE(SUM(a.due), 0) as due,
                    COALESCE(SUM(a.revenue - a.due), 0) as margin,
                    COALESCE(SUM(a.qty), 0) as qty,
                    COUNT(DISTINCT CASE WHEN s.is_star = 1 THEN s.id END) as star_tickets,
                    COALESCE(SUM(CASE WHEN s.is_star = 1 THEN a.revenue ELSE 0 END), 0) as star_revenue
                {from_sql}
                WHERE {where_sql}
                GROUP BY row_val, col_val
                ORDER BY revenue DESC
            """
            raw_rows = [dict(r) for r in c.execute(q_agg, params).fetchall()]

            # Top livre par paire (row_val, col_val)
            q_top = f"""
                WITH book_sales AS (
                    SELECT 
                        {row_expr} as row_val,
                        {col_expr} as col_val,
                        b.title,
                        SUM(a.qty) as book_qty,
                        SUM(a.revenue) as book_rev,
                        ROW_NUMBER() OVER (PARTITION BY {row_expr}, {col_expr} ORDER BY SUM(a.qty) DESC, SUM(a.revenue) DESC) as rn
                    {from_sql}
                    WHERE {where_sql}
                    GROUP BY row_val, col_val, b.id
                )
                SELECT row_val, col_val, title, book_qty, book_rev FROM book_sales WHERE rn = 1
            """
            top_map = {(r["row_val"], r["col_val"]): r for r in c.execute(q_top, params).fetchall()}

            rows_out = []
            distinct_rows = set()
            distinct_cols = set()
            for r in raw_rows:
                rv = r["row_val"]
                cv = r["col_val"]
                distinct_rows.add(rv)
                distinct_cols.add(cv)
                rev = r["revenue"]
                tix = r["tickets"]
                q = r["qty"]
                mrg = r["margin"]
                star_r = r["star_revenue"]
                tb = top_map.get((rv, cv))

                rows_out.append({
                    "row_val": rv,
                    "col_val": cv,
                    "revenue": round(rev, 2),
                    "due": round(r["due"], 2),
                    "margin": round(mrg, 2),
                    "qty": q,
                    "tickets": tix,
                    "avg_basket": round(rev / tix, 2) if tix else 0,
                    "avg_items_per_basket": round(q / tix, 2) if tix else 0,
                    "pct_revenue": round((rev / tot_rev * 100), 1) if tot_rev else 0,
                    "pct_margin": round((mrg / rev * 100), 1) if rev else 0,
                    "star_tickets": r["star_tickets"],
                    "star_revenue": round(star_r, 2),
                    "star_pct": round((star_r / rev * 100), 1) if rev else 0,
                    "top_book": tb["title"] if tb else None,
                    "top_book_qty": tb["book_qty"] if tb else 0,
                    "top_book_rev": round(tb["book_rev"], 2) if tb else 0
                })

            return {
                "total": {
                    "revenue": round(tot_rev, 2),
                    "due": round(tot["total_due"], 2),
                    "margin": round(tot_margin, 2),
                    "qty": tot_qty,
                    "tickets": tot_tickets,
                    "avg_basket": round(tot_rev / tot_tickets, 2) if tot_tickets else 0,
                    "avg_items_per_basket": round(tot_qty / tot_tickets, 2) if tot_tickets else 0,
                    "star_tickets": tot["total_star_tickets"],
                    "star_revenue": round(tot_star_rev, 2),
                    "star_pct": round(tot_star_rev / tot_rev * 100, 1) if tot_rev else 0,
                    "margin_pct": round(tot_margin / tot_rev * 100, 1) if tot_rev else 0,
                },
                "rows": rows_out,
                "dimension_row": row_key,
                "dimension_row_label": row_cfg["label"],
                "dimension_col": col_key,
                "dimension_col_label": col_cfg["label"],
                "distinct_rows": sorted(list(distinct_rows)),
                "distinct_cols": sorted(list(distinct_cols))
            }


# ---------- Excel / sauvegardes ----------
MAX_IMPORT_BYTES = 25 * 1024 * 1024
MAX_UNZIPPED_BYTES = 200 * 1024 * 1024


@app.post("/api/import")
async def import_xlsx(request: Request, file: UploadFile = File(...), replace: bool = True):
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(413, "Fichier trop volumineux (25 Mo maximum)")
    if not data.startswith(b"PK\x03\x04"):
        raise HTTPException(400, "Ce fichier n'est pas un classeur .xlsx valide")
    try:   # protection contre les « zip bombs » avant de confier le fichier à openpyxl
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
            if len(infos) > 2000 or sum(i.file_size for i in infos) > MAX_UNZIPPED_BYTES:
                raise HTTPException(400, "Classeur rejeté : contenu décompressé anormalement volumineux")
            if "[Content_Types].xml" not in z.namelist():
                raise HTTPException(400, "Ce fichier n'est pas un classeur .xlsx valide")
    except zipfile.BadZipFile:
        raise HTTPException(400, "Fichier .xlsx corrompu")
    tmp = os.path.join(db.DATA_DIR, f"_import_{secrets.token_hex(6)}.xlsx")   # nom imprévisible : pas de collision
    with open(tmp, "wb") as f:
        f.write(data)
    try:
        rep = excel_io.import_workbook(tmp, replace)
    finally:
        os.remove(tmp)
    with db.tx() as c:
        db.log_audit(c, get_current_user(request), "IMPORT", "system", None,
                     f"Import Excel « {os.path.basename(file.filename or 'classeur')[:80]} » (remplacement : {'oui' if replace else 'non'})")
    return rep


@app.get("/api/export")
def export_xlsx():
    path = os.path.join(db.DATA_DIR, f"Export_{datetime.now():%Y%m%d_%H%M}.xlsx")
    excel_io.export_workbook(path)
    return FileResponse(path, filename=os.path.basename(path),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


BACKUP_NAME = re.compile(r"^[A-Za-z0-9_\-]{1,120}\.(db|xlsx)$")


def backup_path(filename: str) -> str:
    """Chemin sûr d'un fichier de sauvegarde : nom strict + confinement dans le dossier des sauvegardes.
    Bloque la traversée de répertoires (« ..\\ », « ../ », chemins absolus, ADS Windows, etc.)."""
    if not BACKUP_NAME.fullmatch(filename or ""):
        raise HTTPException(400, "Nom de fichier de sauvegarde invalide")
    root = os.path.realpath(BACKUPS)
    path = os.path.realpath(os.path.join(root, filename))
    if os.path.commonpath([root, path]) != root or os.path.dirname(path) != root:
        raise HTTPException(400, "Nom de fichier de sauvegarde invalide")
    return path


@app.post("/api/backup")
def backup(request: Request):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_db = os.path.join(BACKUPS, f"librairie_{stamp}.db")
    db.safe_backup_db(target_db)

    target_xl = os.path.join(BACKUPS, f"Bibliotheque_{stamp}.xlsx")
    excel_io.export_workbook(target_xl)
    with db.tx() as c:
        db.log_audit(c, get_current_user(request), "BACKUP", "system", None,
                     f"Snapshot manuel créé (librairie_{stamp}.db)")
    return {"ok": True, "filename": f"librairie_{stamp}.db"}


@app.get("/api/backups")
def list_backups():
    """Liste tous les points de restauration existants avec métadonnées."""
    items = []
    if os.path.exists(BACKUPS):
        for fname in os.listdir(BACKUPS):
            if not BACKUP_NAME.fullmatch(fname):
                continue
            fpath = os.path.join(BACKUPS, fname)
            if os.path.isfile(fpath):
                stat = os.stat(fpath)
                kind = "database" if fname.endswith(".db") else "excel"
                items.append({
                    "filename": fname,
                    "kind": kind,
                    "size_bytes": stat.st_size,
                    "size_human": f"{stat.st_size / 1024:.1f} Ko" if stat.st_size < 1024*1024 else f"{stat.st_size / (1024*1024):.2f} Mo",
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(sep=" ", timespec="seconds")
                })
    items.sort(key=lambda x: x["modified"], reverse=True)
    return items


@app.get("/api/backups/{filename}/download")
def download_backup(filename: str):
    fpath = backup_path(filename)
    if not os.path.isfile(fpath):
        raise HTTPException(404, "Fichier de sauvegarde introuvable")
    return FileResponse(fpath, filename=filename)


@app.delete("/api/backups/{filename}")
def delete_backup_file(filename: str, request: Request):
    fpath = backup_path(filename)
    if not os.path.isfile(fpath):
        raise HTTPException(404, "Fichier introuvable")
    os.remove(fpath)
    with db.tx() as c:
        db.log_audit(c, get_current_user(request), "DELETE", "backup", None, f"Suppression fichier de sauvegarde « {filename} »")
    return {"ok": True}


@app.post("/api/backups/{filename}/restore")
def restore_backup(filename: str, request: Request):
    """Restaure une base de données de sauvegarde existante avec copie de sécurité préalable."""
    if not filename.endswith(".db"):
        raise HTTPException(400, "Seules les sauvegardes de base de données (.db) peuvent être restaurées directement")
    fpath = backup_path(filename)
    if not os.path.isfile(fpath):
        raise HTTPException(404, "Fichier de sauvegarde introuvable")

    # 0. Vérifier l'intégrité de la sauvegarde AVANT de toucher à la base courante
    tmp_restore = db.DB_PATH + ".tmp_restore"
    shutil.copyfile(fpath, tmp_restore)
    try:
        import sqlite3
        chk = sqlite3.connect(tmp_restore)
        try:
            ok = chk.execute("PRAGMA quick_check").fetchone()[0] == "ok" and \
                chk.execute("SELECT 1 FROM sqlite_master WHERE name='books'").fetchone() is not None
        finally:
            chk.close()
    except Exception:
        ok = False
    if not ok:
        os.remove(tmp_restore)
        raise HTTPException(400, "Sauvegarde corrompue ou invalide : la base actuelle n'a pas été modifiée")

    # 1. Préserver l'état actuel juste avant restauration
    pre_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_avant_restauration")
    pre_path = os.path.join(BACKUPS, f"librairie_{pre_stamp}.db")
    db.safe_backup_db(pre_path)

    # 2. Remplacer la base de données actuelle (SQLite en mode WAL : remplacement atomique du fichier)
    for extra in (db.DB_PATH + "-wal", db.DB_PATH + "-shm"):
        if os.path.exists(extra):
            try:
                os.remove(extra)
            except OSError:
                pass

    os.replace(tmp_restore, db.DB_PATH)

    with db.tx() as c:
        db.log_audit(c, get_current_user(request), "RESTORE", "system", None,
                     f"Restauration du point #{filename} (Sauvegarde de précaution créée: librairie_{pre_stamp}.db)")

    _dirty.set()  # Forcer la régénération du miroir Excel
    return {"ok": True, "pre_backup": f"librairie_{pre_stamp}.db"}


@app.get("/api/info")
def info():
    """Chemins locaux : réservé au poste de caisse (non listé dans la politique d'accès des téléphones)."""
    return {"data_dir": db.DATA_DIR, "mirror": MIRROR, "backups": BACKUPS}


# ---------- scanner mobile : appairage, recherche, QR local ----------
try:
    from . import certs
except ImportError:      # bibliothèque `cryptography` absente : le poste fonctionne, sans mobile
    certs = None


def _mobile_base():
    port, ips = security.state["https_port"], security.local_ips()
    return f"https://{ips[0]}:{port}" if (port and ips and certs) else None


@app.get("/api/ping")
def ping():
    return {
        "ok": True,
        "time": time.time(),
        "host": socket.gethostname(),
        "mdns_host": f"{socket.gethostname().lower()}.local",
        "ips": security.local_ips()
    }


@app.get("/api/mobile/info")
def mobile_info():
    base = _mobile_base()
    hname = socket.gethostname().lower()
    return {"enabled": bool(base), "base_url": base, "ips": security.local_ips(),
            "mdns_host": f"{hname}.local",
            "ca_fingerprint": certs.ca_fingerprint() if base else None,
            "devices": security.list_devices()}


@app.post("/api/mobile/pairing")
def mobile_pairing():
    base = _mobile_base()
    if not base:
        raise HTTPException(503, "Le mode mobile (HTTPS) n'est pas actif sur ce poste. Lancez Installer_Mobile.bat.")
    code = security.new_pairing_code()
    # Le code est dans le FRAGMENT (#) : il n'est jamais envoyé au serveur ni consigné dans les journaux/Referer
    return {"url": f"{base}/mobile#pair={code}", "expires_in": security.PAIRING_TTL}


@app.post("/api/mobile/pair")
def mobile_pair(body: PairIn, request: Request):
    ip = request.client.host if request.client else "?"
    token = security.redeem_pairing(body.code, body.name, ip)
    if not token:
        raise HTTPException(401, "Code d'appairage invalide ou expiré : affichez un nouveau QR code sur le poste")
    with db.tx() as c:
        db.log_audit(c, "Système", "INSERT", "device", None, f"Téléphone appairé « {(body.name or 'Téléphone')[:60]} » ({ip})")
    return {"token": token}


@app.get("/api/mobile/me")
def mobile_me(request: Request):
    return {"device": request.state.device["name"]}


@app.delete("/api/mobile/devices/{did}")
def mobile_revoke(did: int, request: Request):
    security.revoke_device(did)
    with db.tx() as c:
        db.log_audit(c, get_current_user(request), "DELETE", "device", did, f"Appairage téléphone #{did} révoqué")
    return {"ok": True}


@app.get("/api/ca.crt")
def download_ca():
    """Certificat PUBLIC de la CA locale (jamais de clé privée) à installer sur les téléphones."""
    if not certs:
        raise HTTPException(503, "HTTPS local non disponible")
    return Response(certs.ca_pem(), media_type="application/x-x509-ca-cert",
                    headers={"Content-Disposition": 'attachment; filename="Librairie-CA.crt"'})


@app.get("/api/qr")
def qr_svg(data: str):
    """QR code généré localement : l'URL d'appairage ne quitte jamais le poste (aucun service tiers)."""
    if not data.startswith("https://") or len(data) > 300:
        raise HTTPException(400, "Donnée invalide")
    import segno
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="svg", scale=8, border=2, dark="#000000", light="#ffffff")
    return Response(buf.getvalue(), media_type="image/svg+xml")


def _mobile_book(c, b):
    if b["is_pack"]:
        stock = db.pack_stock(c, b["id"])
        items = db.rows(c, """SELECT pi.book_id, pi.qty, bk.title, bk.price FROM pack_items pi
            JOIN books bk ON bk.id=pi.book_id WHERE pi.pack_id=?""", (b["id"],))
        for it in items:
            it["lots"] = db.rows(c, f"""
                SELECT l.id, l.date, o.name owner, o.color, ({db.LOT_REMAINING}) remaining
                FROM lots l JOIN owners o ON o.id=l.owner_id
                WHERE l.book_id=? AND ({db.LOT_REMAINING}) > 0
                ORDER BY o.priority, l.date, l.id""", (it["book_id"],))
        return {
            "id": b["id"], "code": b["code"], "title": b["title"], "volume": b["volume"], "price": b["price"],
            "is_pack": 1, "lots": [], "stock": stock, "items": items, "suggested_packs": []
        }

    lots = db.rows(c, f"""
        SELECT l.id, l.date, o.name owner, o.color, ({db.LOT_REMAINING}) remaining
        FROM lots l JOIN owners o ON o.id=l.owner_id
        WHERE l.book_id=? AND ({db.LOT_REMAINING}) > 0
        ORDER BY o.priority, l.date, l.id""", (b["id"],))

    raw_packs = db.rows(c, """
        SELECT p.id, p.code, p.title, p.price,
               (SELECT SUM(bk.price * pi2.qty) FROM pack_items pi2 JOIN books bk ON bk.id = pi2.book_id WHERE pi2.pack_id = p.id) separate_price,
               (SELECT GROUP_CONCAT(bk2.title, ' + ') FROM pack_items pi3 JOIN books bk2 ON bk2.id = pi3.book_id WHERE pi3.pack_id = p.id AND bk2.id != ?) other_items
        FROM pack_items pi
        JOIN books p ON p.id = pi.pack_id
        WHERE pi.book_id = ? AND p.active = 1
    """, (b["id"], b["id"]))

    suggested_packs = []
    for sp in raw_packs:
        sp_stock = db.pack_stock(c, sp["id"])
        saving = round(float(sp["separate_price"] or 0) - float(sp["price"] or 0), 2)
        sp_items = db.rows(c, """SELECT pi.book_id, pi.qty, bk.title, bk.price FROM pack_items pi
            JOIN books bk ON bk.id=pi.book_id WHERE pi.pack_id=?""", (sp["id"],))
        for it in sp_items:
            it["lots"] = db.rows(c, f"""
                SELECT l.id, l.date, o.name owner, o.color, ({db.LOT_REMAINING}) remaining
                FROM lots l JOIN owners o ON o.id=l.owner_id
                WHERE l.book_id=? AND ({db.LOT_REMAINING}) > 0
                ORDER BY o.priority, l.date, l.id""", (it["book_id"],))
        suggested_packs.append({
            "id": sp["id"],
            "code": sp["code"],
            "title": sp["title"],
            "price": sp["price"],
            "separate_price": sp["separate_price"],
            "other_items": sp["other_items"] or "",
            "saving": saving,
            "stock": sp_stock,
            "is_pack": 1,
            "items": sp_items
        })

    return {
        "id": b["id"], "code": b["code"], "title": b["title"], "volume": b["volume"], "price": b["price"],
        "is_pack": 0, "lots": lots, "stock": sum(l["remaining"] for l in lots),
        "suggested_packs": suggested_packs
    }


@app.get("/api/books/scan/{code}")
def scan_book(code: str):
    """Recherche EXACTE par code-barres (ISBN/EAN). Jamais de recherche approximative : un scan ne doit
    pas pouvoir ajouter un mauvais livre au panier."""
    clean = code.strip()[:40]
    plain = clean.replace("-", "").replace(" ", "")
    with db.tx() as c:
        book = c.execute("""SELECT * FROM books WHERE active=1 AND
            (code = ? OR REPLACE(REPLACE(code,'-',''),' ','') = ?) LIMIT 1""", (clean, plain)).fetchone()
        if not book:
            raise HTTPException(404, f"Aucun livre pour le code « {clean} »")
        return _mobile_book(c, book)


@app.get("/api/books/search")
def search_books(q: str):
    """Recherche textuelle (saisie manuelle quand le code-barres est illisible) : 8 résultats maximum."""
    q = q.strip()[:60]
    if len(q) < 2:
        return []
    like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with db.tx() as c:
        rows = c.execute("""SELECT * FROM books WHERE active=1 AND
            (title LIKE ? ESCAPE '\\' OR code LIKE ? ESCAPE '\\' OR author LIKE ? ESCAPE '\\' OR series LIKE ? ESCAPE '\\')
            ORDER BY title LIMIT 8""", (like, like, like, like)).fetchall()
        return [_mobile_book(c, r) for r in rows]


@app.get("/mobile")
def mobile_view():
    return FileResponse(os.path.join(STATIC, "mobile.html"))


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")
