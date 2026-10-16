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


class SaleIn(BaseModel):
    date: Optional[str] = Field(None, pattern=DATE_PATTERN)
    payment: Optional[str] = Field("Espèces", max_length=60)
    note: Optional[str] = Field(None, max_length=300)
    customer_gender: Optional[str] = Field(None, max_length=20)
    customer_age_group: Optional[str] = Field(None, max_length=40)
    is_star: Optional[int] = 0
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
    for b in bl:
        b["by_owner"] = byo.get(b["id"], [])
        b["lots"] = lots_by.get(b["id"], [])
        if b["is_pack"]:
            b["stock"] = db.pack_stock(c, b["id"])
            b["items"] = db.rows(c, """SELECT pi.book_id,pi.qty,bk.title FROM pack_items pi
                JOIN books bk ON bk.id=pi.book_id WHERE pi.pack_id=?""", (b["id"],))
            for it in b["items"]:
                it["lots"] = lots_by.get(it["book_id"], [])
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
    is_paypal = "paypal" in (s.payment or "").lower()
    
    with db.tx() as c:
        # Restriction PayPal POS : réservé exclusivement aux articles appartenant à Cité Royale
        if is_paypal:
            for l in s.lines:
                allocs = l.allocations or []
                for a in allocs:
                    if a.lot_id is not None:
                        ow = c.execute("SELECT o.name FROM lots l JOIN owners o ON o.id=l.owner_id WHERE l.id=?", (a.lot_id,)).fetchone()
                        if ow and ow["name"].strip().lower() != "cité royale":
                            raise HTTPException(400, f"Le paiement PayPal POS est exclusivement réservé aux ouvrages de « Cité Royale ». L'article sélectionné provient de « {ow['name']} ».")

        sid, warns = db.create_sale(c, s.date, s.payment, s.note, [l.dict() for l in s.lines],
                                    manual=True, user_name=user,
                                    customer_gender=s.customer_gender,
                                    customer_age_group=s.customer_age_group,
                                    is_star=s.is_star or 0)
        total = sum((l.unit_price if l.unit_price is not None else
                     c.execute("SELECT price FROM books WHERE id=?", (l.book_id,)).fetchone()["price"]) * l.qty for l in s.lines)
        db.log_audit(c, user, "INSERT", "sale", sid,
                     f"Vente #{sid} : {total:.2f} € ({len(s.lines)} article(s), {s.payment}) par {user}",
                     snapshot_after={"id": sid, "date": s.date, "total": total, "payment": s.payment, "user_name": user,
                                     "customer_gender": s.customer_gender, "customer_age_group": s.customer_age_group,
                                     "is_star": s.is_star, "lines": [l.dict() for l in s.lines]})
    return {"id": sid, "total": total, "warnings": warns}


@app.get("/api/sales")
def sales(limit: int = 200):
    with db.tx() as c:
        return db.rows(c, """SELECT s.id,s.date,s.payment,s.note,COALESCE(s.user_name,'Anonyme') user_name,
            s.customer_gender, s.customer_age_group, COALESCE(s.is_star, 0) is_star,
            SUM(l.qty*l.unit_price) total, SUM(l.qty) qty,
            GROUP_CONCAT(l.qty||'× '||b.title, ' · ') detail
            FROM sales s JOIN sale_lines l ON l.sale_id=s.id JOIN books b ON b.id=l.book_id
            GROUP BY s.id ORDER BY s.date DESC, s.id DESC LIMIT ?""", (limit,))


@app.delete("/api/sales/{sid}")
def sale_del(sid: int, request: Request):
    with db.tx() as c:
        sale = c.execute("SELECT * FROM sales WHERE id=?", (sid,)).fetchone()
        if sale:
            c.execute("DELETE FROM sales WHERE id=?", (sid,))
            db.log_audit(c, get_current_user(request), "DELETE", "sale", sid, f"Suppression/annulation vente #{sid}", snapshot_before=dict(sale))
    return {"ok": True}


# ---------- trésorerie & caisse ----------
@app.get("/api/treasury")
def treasury_summary():
    with db.tx() as c:
        # 1. Total par mode de paiement dans les ventes
        sales_by_pay = db.rows(c, """
            SELECT payment, COALESCE(SUM(l.qty * l.unit_price), 0) total, COUNT(DISTINCT s.id) count
            FROM sales s
            JOIN sale_lines l ON l.sale_id = s.id
            GROUP BY payment
        """)
        
        # 2. Total des mouvements de caisse enregistrés
        movements = db.rows(c, "SELECT * FROM cash_movements ORDER BY date DESC, id DESC")
        
        # 3. Calcul de la caisse physique locale (ICC Rennes)
        # RÈGLE MÉTIER : 100% de Cité Royale revient à Cité Royale et ne va JAMAIS dans la trésorerie / caisse locale.
        # Seules les ventes en espèces provenant d'exemplaires NON Cité Royale (ex: ICC Rennes) alimentent la caisse physique.
        sales_cash = c.execute("""
            SELECT COALESCE(SUM(a.revenue), 0) s
            FROM sales s
            JOIN sale_lines l ON l.sale_id = s.id
            JOIN allocations a ON a.line_id = l.id
            JOIN owners o ON o.id = a.owner_id
            WHERE s.payment LIKE '%Espèce%' AND LOWER(TRIM(o.name)) != 'cité royale'
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

        # Total Cité Royale payé directement sur PayPal POS
        cr_paypal_total = c.execute("""
            SELECT COALESCE(SUM(a.revenue), 0) s
            FROM sales s
            JOIN sale_lines l ON l.sale_id = s.id
            JOIN allocations a ON a.line_id = l.id
            JOIN owners o ON o.id = a.owner_id
            WHERE s.payment LIKE '%PayPal%' AND LOWER(TRIM(o.name)) = 'cité royale'
        """).fetchone()["s"]

        # Total Cité Royale encaissé hors PayPal (que les libraires doivent passer sur PayPal POS)
        cr_non_paypal_total = c.execute("""
            SELECT COALESCE(SUM(a.revenue), 0) s
            FROM sales s
            JOIN sale_lines l ON l.sale_id = s.id
            JOIN allocations a ON a.line_id = l.id
            JOIN owners o ON o.id = a.owner_id
            WHERE s.payment NOT LIKE '%PayPal%' AND LOWER(TRIM(o.name)) = 'cité royale'
        """).fetchone()["s"]
        
        # 4. Solde & Dettes par utilisateur / libraire
        users = [u["name"] for u in db.rows(c, "SELECT name FROM users ORDER BY name")]
        extra_users = [r["u"] for r in db.rows(c, "SELECT DISTINCT user_name u FROM sales WHERE user_name IS NOT NULL AND user_name != '' UNION SELECT DISTINCT user_name u FROM cash_movements")]
        all_user_names = sorted(list(set(users + extra_users)))
        
        user_balances = []
        for uname in all_user_names:
            # Ventes totales encaissées par ce libraire pour Cité Royale hors PayPal POS
            # (Le libraire doit payer lui-même ce montant sur la borne PayPal POS pour régulariser Cité Royale)
            cr_due_to_paypal = c.execute("""
                SELECT COALESCE(SUM(a.revenue), 0) s
                FROM sales s
                JOIN sale_lines l ON l.sale_id = s.id
                JOIN allocations a ON a.line_id = l.id
                JOIN owners o ON o.id = a.owner_id
                WHERE s.user_name = ? AND s.payment NOT LIKE '%PayPal%' AND LOWER(TRIM(o.name)) = 'cité royale'
            """, (uname,)).fetchone()["s"]

            # Ventes ICC Rennes encaissées sur compte personnel (Wero / virement perso)
            # (Le libraire doit régulariser et déposer ce montant dans la caisse physique)
            icc_wero_received = c.execute("""
                SELECT COALESCE(SUM(a.revenue), 0) s
                FROM sales s
                JOIN sale_lines l ON l.sale_id = s.id
                JOIN allocations a ON a.line_id = l.id
                JOIN owners o ON o.id = a.owner_id
                WHERE s.user_name = ? AND (s.payment LIKE '%Wero%' OR s.payment LIKE '%perso%') AND LOWER(TRIM(o.name)) != 'cité royale'
            """, (uname,)).fetchone()["s"]

            # Ventes totales tous canaux Wero (pour information)
            wero_received = c.execute("""
                SELECT COALESCE(SUM(l.qty * l.unit_price), 0) s
                FROM sales s JOIN sale_lines l ON l.sale_id = s.id
                WHERE s.user_name = ? AND (s.payment LIKE '%Wero%' OR s.payment LIKE '%perso%')
            """, (uname,)).fetchone()["s"]
            
            # Ventes où le libraire a encaissé des espèces (toutes origines)
            cash_received = c.execute("""
                SELECT COALESCE(SUM(l.qty * l.unit_price), 0) s
                FROM sales s JOIN sale_lines l ON l.sale_id = s.id
                WHERE s.user_name = ? AND s.payment LIKE '%Espèce%'
            """, (uname,)).fetchone()["s"]
            
            # Ventes payées directement via PayPal POS
            paypal_sales = c.execute("""
                SELECT COALESCE(SUM(l.qty * l.unit_price), 0) s
                FROM sales s JOIN sale_lines l ON l.sale_id = s.id
                WHERE s.user_name = ? AND s.payment LIKE '%PayPal%'
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
def stats(start: Optional[str] = None, end: Optional[str] = None):
    start = start or "0000-00-00"
    end = end or "9999-12-31"
    with db.tx() as c:
        W, A = "a.date BETWEEN ? AND ?", (start, end)
        k = c.execute(f"SELECT COALESCE(SUM(revenue),0) rev,COALESCE(SUM(due),0) due,COALESCE(SUM(qty),0) qty FROM allocations a WHERE {W}", A).fetchone()
        nb = c.execute("SELECT COUNT(*) n FROM sales WHERE date BETWEEN ? AND ?", A).fetchone()["n"]
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
        pay = db.rows(c, "SELECT payment label, COUNT(*) n FROM sales WHERE date BETWEEN ? AND ? GROUP BY payment", A)
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
            WHERE s.date BETWEEN ? AND ? AND (s.note IS NULL OR s.note != 'Import Excel')
        """, A).fetchone()
        pos_nb = pos_sales["n"]
        pos_rev = pos_sales["rev"]
        pos_avg_basket = (pos_rev / pos_nb) if pos_nb else 0
        avg_book_price = (k["rev"] / k["qty"]) if k["qty"] else 0

        # Répartition démographique anonyme (Ventes caisse qualifiées)
        by_gender = db.rows(c, f"""
            SELECT COALESCE(customer_gender, 'Non renseigné') label,
                   COUNT(DISTINCT s.id) n,
                   COALESCE(SUM(l.qty * l.unit_price), 0) revenue
            FROM sales s
            JOIN sale_lines l ON l.sale_id = s.id
            WHERE s.date BETWEEN ? AND ? AND (s.note IS NULL OR s.note != 'Import Excel')
            GROUP BY label ORDER BY revenue DESC
        """, A)

        by_age = db.rows(c, f"""
            SELECT COALESCE(customer_age_group, 'Non renseigné') label,
                   COUNT(DISTINCT s.id) n,
                   COALESCE(SUM(l.qty * l.unit_price), 0) revenue
            FROM sales s
            JOIN sale_lines l ON l.sale_id = s.id
            WHERE s.date BETWEEN ? AND ? AND (s.note IS NULL OR s.note != 'Import Excel')
            GROUP BY label ORDER BY revenue DESC
        """, A)

        by_star = db.rows(c, f"""
            SELECT CASE WHEN s.is_star = 1 THEN 'Serviteur STAR ⭐' ELSE 'Autre fidèle / Visiteur' END label,
                   COUNT(DISTINCT s.id) n,
                   COALESCE(SUM(l.qty * l.unit_price), 0) revenue
            FROM sales s
            JOIN sale_lines l ON l.sale_id = s.id
            WHERE s.date BETWEEN ? AND ? AND (s.note IS NULL OR s.note != 'Import Excel')
            GROUP BY (s.is_star = 1) ORDER BY (s.is_star = 1) DESC
        """, A)

        return {"kpi": {"revenue": k["rev"], "due": k["due"], "margin": k["rev"] - k["due"], "qty": k["qty"],
                        "sales": nb, "pos_sales": pos_nb, "pos_avg_basket": pos_avg_basket,
                        "avg_book_price": avg_book_price,
                        "avg_basket": (k["rev"] / nb) if nb else 0,
                        "stock_value": sv["v"], "stock_units": sv["u"], "due_open": due_open},
                "monthly": monthly, "by_owner_month": by_owner_month, "forecast": fc,
                "daily": daily, "top": top, "by_category": by_cat, "by_publisher": by_pub, "by_owner": by_owner,
                "payments": pay, "weekday": wd, "by_gender": by_gender, "by_age": by_age, "by_star": by_star, "low_stock": low[:30]}


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


@app.get("/api/mobile/info")
def mobile_info():
    base = _mobile_base()
    return {"enabled": bool(base), "base_url": base, "ips": security.local_ips(),
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
    lots = db.rows(c, f"""
        SELECT l.id, l.date, o.name owner, o.color, ({db.LOT_REMAINING}) remaining
        FROM lots l JOIN owners o ON o.id=l.owner_id
        WHERE l.book_id=? AND ({db.LOT_REMAINING}) > 0
        ORDER BY o.priority, l.date, l.id""", (b["id"],))
    return {"id": b["id"], "code": b["code"], "title": b["title"], "volume": b["volume"], "price": b["price"],
            "is_pack": b["is_pack"], "lots": lots, "stock": sum(l["remaining"] for l in lots)}


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
