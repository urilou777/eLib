"""API FastAPI locale – Librairie."""
import os
import sys
import threading
import time
import shutil
from datetime import date, datetime, timedelta
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
from . import db, excel_io

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


class LotIn(BaseModel):
    book_id: int
    owner_id: int
    qty_in: int
    date: Optional[str] = None
    unit_cost: Optional[float] = None
    reverse_pct: Optional[float] = None
    note: Optional[str] = None


class AdjIn(BaseModel):
    delta: int
    reason: Optional[str] = "Ajustement"
    date: Optional[str] = None


class AllocIn(BaseModel):
    book_id: Optional[int] = None   # composant (packs) ; vide = le livre de la ligne
    lot_id: Optional[int] = None    # None = vente hors stock (explicite)
    qty: int


class LineIn(BaseModel):
    book_id: int
    qty: int = 1
    unit_price: Optional[float] = None
    allocations: List[AllocIn] = []


class SaleIn(BaseModel):
    date: Optional[str] = None
    payment: Optional[str] = "Espèces"
    note: Optional[str] = None
    lines: List[LineIn]


class CashMovementIn(BaseModel):
    user_name: str
    type: str                  # 'DEPOSIT' | 'WITHDRAWAL' | 'ADJUST'
    channel: str               # 'ESPECES' | 'WERO' | 'PAYPAL'
    amount: float
    date: Optional[str] = None
    note: Optional[str] = None


class SettleIn(BaseModel):
    owner_id: int
    amount: float
    date: Optional[str] = None
    note: Optional[str] = None


class ResIn(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    qty: int = 1
    status: str = "En attente"
    note: Optional[str] = None


class DropdownItemIn(BaseModel):
    group_key: str
    label: str


class UserIn(BaseModel):
    name: str


def get_current_user(request: Request) -> str:
    """Récupère l'utilisateur transmis par le client dans l'en-tête X-User ou query, sinon 'Anonyme'."""
    u = request.headers.get("X-User") or request.query_params.get("user")
    return u.strip() if u and u.strip() else "Anonyme"


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


@app.delete("/api/options/{opt_id}")
def delete_option(opt_id: int, request: Request):
    with db.tx() as c:
        old = c.execute("SELECT * FROM dropdown_options WHERE id=?", (opt_id,)).fetchone()
        if old:
            c.execute("DELETE FROM dropdown_options WHERE id=?", (opt_id,))
            db.log_audit(c, get_current_user(request), "DELETE", "option", opt_id, f"Suppression option {old['group_key']}: « {old['label']} »", snapshot_before=dict(old))
    return {"ok": True}


# ---------- propriétaires ----------
@app.get("/api/owners")
def owners():
    with db.tx() as c:
        return db.rows(c, "SELECT * FROM owners ORDER BY priority,name")


@app.post("/api/owners")
def owner_add(o: OwnerIn):
    with db.tx() as c:
        c.execute("INSERT INTO owners(name,kind,reverse_pct,priority,color) VALUES(?,?,?,?,?)",
                  (o.name, o.kind, o.reverse_pct, o.priority, o.color))
    return {"ok": True}


@app.put("/api/owners/{oid}")
def owner_upd(oid: int, o: OwnerIn):
    with db.tx() as c:
        c.execute("UPDATE owners SET name=?,kind=?,reverse_pct=?,priority=?,color=? WHERE id=?",
                  (o.name, o.kind, o.reverse_pct, o.priority, o.color, oid))
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
    user = get_current_user(request)
    with db.tx() as c:
        sid, warns = db.create_sale(c, s.date, s.payment, s.note, [l.dict() for l in s.lines], manual=True, user_name=user)
        total = sum((l.unit_price if l.unit_price is not None else
                     c.execute("SELECT price FROM books WHERE id=?", (l.book_id,)).fetchone()["price"]) * l.qty for l in s.lines)
        db.log_audit(c, user, "INSERT", "sale", sid,
                     f"Vente #{sid} : {total:.2f} € ({len(s.lines)} article(s), {s.payment}) par {user}",
                     snapshot_after={"id": sid, "date": s.date, "total": total, "payment": s.payment, "user_name": user, "lines": [l.dict() for l in s.lines]})
    return {"id": sid, "total": total, "warnings": warns}


@app.get("/api/sales")
def sales(limit: int = 200):
    with db.tx() as c:
        return db.rows(c, """SELECT s.id,s.date,s.payment,s.note,COALESCE(s.user_name,'Anonyme') user_name,
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
        
        # 3. Calcul de la caisse physique (Espèces)
        # Entrées en espèces directes des ventes
        sales_cash = c.execute("""
            SELECT COALESCE(SUM(l.qty * l.unit_price), 0) s
            FROM sales s JOIN sale_lines l ON l.sale_id = s.id
            WHERE s.payment LIKE '%Espèce%'
        """).fetchone()["s"]
        
        # Dépôts d'espèces régularisés en caisse par les libraires (ex: conversion de leurs encaissements Wero)
        deposits_cash = c.execute("""
            SELECT COALESCE(SUM(amount), 0) s FROM cash_movements WHERE type = 'DEPOSIT' AND channel = 'ESPECES'
        """).fetchone()["s"]
        
        # Sorties de caisse (remboursements aux libraires qui ont avancé leurs fonds ou retraits)
        withdrawals_cash = c.execute("""
            SELECT COALESCE(SUM(amount), 0) s FROM cash_movements WHERE type = 'WITHDRAWAL' AND channel = 'ESPECES'
        """).fetchone()["s"]
        
        cash_in_drawer = sales_cash + deposits_cash - withdrawals_cash
        
        # 4. Solde & Dettes par utilisateur / libraire
        # Quels utilisateurs ont encaissé quoi ?
        users = [u["name"] for u in db.rows(c, "SELECT name FROM users ORDER BY name")]
        # On inclut aussi les noms trouvés dans les ventes ou mouvements
        extra_users = [r["u"] for r in db.rows(c, "SELECT DISTINCT user_name u FROM sales WHERE user_name IS NOT NULL AND user_name != '' UNION SELECT DISTINCT user_name u FROM cash_movements")]
        all_user_names = sorted(list(set(users + extra_users)))
        
        user_balances = []
        for uname in all_user_names:
            # Ventes encaissées sur le compte perso du libraire (Wero / Virement perso)
            wero_received = c.execute("""
                SELECT COALESCE(SUM(l.qty * l.unit_price), 0) s
                FROM sales s JOIN sale_lines l ON l.sale_id = s.id
                WHERE s.user_name = ? AND (s.payment LIKE '%Wero%' OR s.payment LIKE '%perso%')
            """, (uname,)).fetchone()["s"]
            
            # Ventes où le libraire a encaissé des espèces en main propre
            cash_received = c.execute("""
                SELECT COALESCE(SUM(l.qty * l.unit_price), 0) s
                FROM sales s JOIN sale_lines l ON l.sale_id = s.id
                WHERE s.user_name = ? AND s.payment LIKE '%Espèce%'
            """, (uname,)).fetchone()["s"]
            
            # Ventes payées via PayPal POS (borne Cité Royale)
            paypal_sales = c.execute("""
                SELECT COALESCE(SUM(l.qty * l.unit_price), 0) s
                FROM sales s JOIN sale_lines l ON l.sale_id = s.id
                WHERE s.user_name = ? AND s.payment LIKE '%PayPal%'
            """, (uname,)).fetchone()["s"]
            
            # Montant déjà déposé dans la caisse par ce libraire
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
            
            # Dette nette : ce que le libraire a encaissé sur son compte personnel (Wero) ou doit déposer,
            # moins ce qu'il a déjà déposé dans la caisse physique, plus ce qu'il a retiré.
            net_to_deposit = wero_received - deposited + withdrawn
            
            user_balances.append({
                "user_name": uname,
                "wero_received": wero_received,
                "cash_received": cash_received,
                "paypal_sales": paypal_sales,
                "deposited": deposited,
                "withdrawn": withdrawn,
                "net_to_deposit": net_to_deposit
            })
            
        return {
            "cash_in_drawer": cash_in_drawer,
            "sales_cash": sales_cash,
            "deposits_cash": deposits_cash,
            "withdrawals_cash": withdrawals_cash,
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
        return {"kpi": {"revenue": k["rev"], "due": k["due"], "margin": k["rev"] - k["due"], "qty": k["qty"],
                        "sales": nb, "avg_basket": (k["rev"] / nb) if nb else 0,
                        "stock_value": sv["v"], "stock_units": sv["u"], "due_open": due_open},
                "monthly": monthly, "by_owner_month": by_owner_month, "forecast": fc,
                "daily": daily, "top": top, "by_category": by_cat, "by_publisher": by_pub, "by_owner": by_owner,
                "payments": pay, "weekday": wd, "low_stock": low[:30]}


# ---------- Excel / sauvegardes ----------
@app.post("/api/import")
async def import_xlsx(file: UploadFile = File(...), replace: bool = True):
    tmp = os.path.join(db.DATA_DIR, "_import.xlsx")
    with open(tmp, "wb") as f:
        f.write(await file.read())
    try:
        rep = excel_io.import_workbook(tmp, replace)
    finally:
        os.remove(tmp)
    return rep


@app.get("/api/export")
def export_xlsx():
    path = os.path.join(db.DATA_DIR, f"Export_{datetime.now():%Y%m%d_%H%M}.xlsx")
    excel_io.export_workbook(path)
    return FileResponse(path, filename=os.path.basename(path),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/api/backup")
def backup(request: Request):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_db = os.path.join(BACKUPS, f"librairie_{stamp}.db")
    db.safe_backup_db(target_db)
    
    target_xl = os.path.join(BACKUPS, f"Bibliotheque_{stamp}.xlsx")
    excel_io.export_workbook(target_xl)
    
@app.get("/api/backups")
def list_backups():
    """Liste tous les points de restauration existants avec métadonnées."""
    items = []
    if os.path.exists(BACKUPS):
        for fname in os.listdir(BACKUPS):
            if fname.endswith(".tmp"):
                continue
            fpath = os.path.join(BACKUPS, fname)
            if os.path.isfile(fpath):
                stat = os.stat(fpath)
                kind = "database" if fname.endswith(".db") else ("excel" if fname.endswith(".xlsx") else "other")
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
    fpath = os.path.join(BACKUPS, filename)
    if not os.path.exists(fpath) or not os.path.isfile(fpath) or filename.endswith(".tmp"):
        raise HTTPException(404, "Fichier de sauvegarde introuvable")
    return FileResponse(fpath, filename=filename)


@app.delete("/api/backups/{filename}")
def delete_backup_file(filename: str, request: Request):
    fpath = os.path.join(BACKUPS, filename)
    if not os.path.exists(fpath) or not os.path.isfile(fpath):
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
    fpath = os.path.join(BACKUPS, filename)
    if not os.path.exists(fpath):
        raise HTTPException(404, "Fichier de sauvegarde introuvable")
    
    # 1. Préserver l'état actuel juste avant restauration
    pre_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_avant_restauration")
    pre_path = os.path.join(BACKUPS, f"librairie_{pre_stamp}.db")
    db.safe_backup_db(pre_path)
    
    # 2. Remplacer la base de données actuelle
    # Pour SQLite en mode WAL, écriture dans un .tmp puis remplacement
    tmp_restore = db.DB_PATH + ".tmp_restore"
    shutil.copyfile(fpath, tmp_restore)
    
    # Supprimer les journaux WAL/SHM actuels s'ils existent
    for extra in (db.DB_PATH + "-wal", db.DB_PATH + "-shm"):
        if os.path.exists(extra):
            try:
                os.remove(extra)
            except OSError:
                pass
                
    os.replace(tmp_restore, db.DB_PATH)
    
    # Réinitialiser la connexion et tracer
    with db.tx() as c:
        db.log_audit(c, get_current_user(request), "RESTORE", "system", None,
                     f"Restauration du point #{filename} (Sauvegarde de précaution créée: librairie_{pre_stamp}.db)")
        
    _dirty.set()  # Forcer la régénération du miroir Excel
    return {"ok": True, "pre_backup": f"librairie_{pre_stamp}.db"}


@app.get("/api/info")
def info():
    return {"data_dir": db.DATA_DIR, "mirror": MIRROR, "backups": BACKUPS}


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")
