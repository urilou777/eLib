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
    """Excel toujours à jour en arrière-plan (miroir) + archive quotidienne."""
    last_day = None
    while True:
        time.sleep(5)
        today = date.today().isoformat()
        if _dirty.is_set() or last_day != today:
            _dirty.clear()
            try:
                excel_io.export_workbook(MIRROR)
                if last_day != today:
                    shutil.copy(MIRROR, os.path.join(BACKUPS, f"Bibliotheque_{today}.xlsx"))
                    shutil.copy(db.DB_PATH, os.path.join(BACKUPS, f"librairie_{today}.db"))
                    last_day = today
                else:
                    shutil.copy(MIRROR, os.path.join(BACKUPS, f"Bibliotheque_{today}.xlsx"))
            except Exception as e:  # ne jamais bloquer l'application
                print("Miroir Excel:", e)


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
def book_add(b: BookIn):
    with db.tx() as c:
        try:
            cur = c.execute("""INSERT INTO books(code,title,series,volume,author,publisher,category,type,location,price,min_stock,is_pack)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (b.code, b.title, b.series, b.volume, b.author, b.publisher,
                                                     b.category, b.type, b.location, b.price, b.min_stock, b.is_pack))
        except Exception:
            raise HTTPException(400, "Ce code existe déjà")
        return {"id": cur.lastrowid}


@app.put("/api/books/{bid}")
def book_upd(bid: int, b: BookIn):
    with db.tx() as c:
        c.execute("""UPDATE books SET code=?,title=?,series=?,volume=?,author=?,publisher=?,category=?,type=?,
            location=?,price=?,min_stock=? WHERE id=?""", (b.code, b.title, b.series, b.volume, b.author,
                                                           b.publisher, b.category, b.type, b.location, b.price, b.min_stock, bid))
    return {"ok": True}


@app.delete("/api/books/{bid}")
def book_del(bid: int):
    with db.tx() as c:
        c.execute("UPDATE books SET active=0 WHERE id=?", (bid,))
    return {"ok": True}


@app.put("/api/books/{bid}/pack")
def pack_set(bid: int, items: List[PackItem]):
    with db.tx() as c:
        c.execute("DELETE FROM pack_items WHERE pack_id=?", (bid,))
        for i in items:
            c.execute("INSERT INTO pack_items(pack_id,book_id,qty) VALUES(?,?,?) ON CONFLICT(pack_id,book_id) DO UPDATE SET qty=qty+excluded.qty",
                      (bid, i.book_id, max(1, i.qty)))
    return {"ok": True}


# ---------- lots (entrées de stock) ----------
@app.get("/api/books/{bid}/lots")
def lots(bid: int):
    with db.tx() as c:
        return db.rows(c, f"""SELECT l.*, o.name owner, o.color, o.reverse_pct o_pct, ({db.LOT_REMAINING}) remaining
            FROM lots l JOIN owners o ON o.id=l.owner_id WHERE l.book_id=? ORDER BY l.date DESC""", (bid,))


@app.post("/api/lots")
def lot_add(l: LotIn):
    with db.tx() as c:
        c.execute("INSERT INTO lots(book_id,owner_id,date,qty_in,unit_cost,reverse_pct,note) VALUES(?,?,?,?,?,?,?)",
                  (l.book_id, l.owner_id, l.date or date.today().isoformat(), l.qty_in, l.unit_cost, l.reverse_pct, l.note))
    return {"ok": True}


@app.post("/api/lots/{lid}/adjust")
def lot_adjust(lid: int, a: AdjIn):
    with db.tx() as c:
        c.execute("INSERT INTO adjustments(lot_id,date,delta,reason) VALUES(?,?,?,?)",
                  (lid, a.date or date.today().isoformat(), a.delta, a.reason))
    return {"ok": True}


# ---------- ventes ----------
@app.post("/api/sales")
def sale_add(s: SaleIn):
    with db.tx() as c:
        sid, warns = db.create_sale(c, s.date, s.payment, s.note, [l.dict() for l in s.lines], manual=True)
        total = sum((l.unit_price if l.unit_price is not None else
                     c.execute("SELECT price FROM books WHERE id=?", (l.book_id,)).fetchone()["price"]) * l.qty for l in s.lines)
    return {"id": sid, "total": total, "warnings": warns}


@app.get("/api/sales")
def sales(limit: int = 200):
    with db.tx() as c:
        return db.rows(c, """SELECT s.id,s.date,s.payment,s.note,
            SUM(l.qty*l.unit_price) total, SUM(l.qty) qty,
            GROUP_CONCAT(l.qty||'× '||b.title, ' · ') detail
            FROM sales s JOIN sale_lines l ON l.sale_id=s.id JOIN books b ON b.id=l.book_id
            GROUP BY s.id ORDER BY s.date DESC, s.id DESC LIMIT ?""", (limit,))


@app.delete("/api/sales/{sid}")
def sale_del(sid: int):
    with db.tx() as c:
        c.execute("DELETE FROM sales WHERE id=?", (sid,))
    return {"ok": True}


# ---------- reversements ----------
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
def settle(s: SettleIn):
    with db.tx() as c:
        c.execute("INSERT INTO settlements(owner_id,date,amount,note) VALUES(?,?,?,?)",
                  (s.owner_id, s.date or date.today().isoformat(), s.amount, s.note))
    return {"ok": True}


# ---------- réservations ----------
@app.get("/api/reservations")
def res_list():
    with db.tx() as c:
        return db.rows(c, "SELECT * FROM reservations ORDER BY status='Servie', id DESC")


@app.post("/api/reservations")
def res_add(r: ResIn):
    with db.tx() as c:
        c.execute("INSERT INTO reservations(name,phone,title,qty,date,status,note) VALUES(?,?,?,?,?,?,?)",
                  (r.name, r.phone, r.title, r.qty, date.today().isoformat(), r.status, r.note))
    return {"ok": True}


@app.put("/api/reservations/{rid}")
def res_upd(rid: int, r: ResIn):
    with db.tx() as c:
        c.execute("UPDATE reservations SET name=?,phone=?,title=?,qty=?,status=?,note=? WHERE id=?",
                  (r.name, r.phone, r.title, r.qty, r.status, r.note, rid))
    return {"ok": True}


@app.delete("/api/reservations/{rid}")
def res_del(rid: int):
    with db.tx() as c:
        c.execute("DELETE FROM reservations WHERE id=?", (rid,))
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
def backup():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy(db.DB_PATH, os.path.join(BACKUPS, f"librairie_{stamp}.db"))
    excel_io.export_workbook(os.path.join(BACKUPS, f"Bibliotheque_{stamp}.xlsx"))
    return {"folder": BACKUPS}


@app.get("/api/info")
def info():
    return {"data_dir": db.DATA_DIR, "mirror": MIRROR, "backups": BACKUPS}


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC), name="static")
