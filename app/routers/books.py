"""
app/routers/books.py
-------------------------------------------------------------------------------
Routeur FastAPI dédié aux opérations sur les livres, packs, lots et statistiques d'ouvrages.
-------------------------------------------------------------------------------
"""

import re
from datetime import date, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from .. import db

router = APIRouter(prefix="/api/books", tags=["books"])

DATE_PATTERN = r"^(\d{4}-\d{2}-\d{2})?$"


def _dump(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    if hasattr(model, "dict"):
        return model.dict()
    return dict(model)


def get_current_user(request: Request) -> str:
    from urllib.parse import unquote
    raw = request.headers.get("X-User") or request.query_params.get("user") or ""
    u = re.sub(r"[\x00-\x1f\x7f<>]", "", unquote(raw)).strip()[:60]
    return u or "Anonyme"


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


@router.get("")
def books_list():
    with db.tx() as c:
        return _books(c)


@router.post("")
def book_add(b: BookIn, request: Request):
    with db.tx() as c:
        try:
            cur = c.execute("""INSERT INTO books(code,title,series,volume,author,publisher,category,type,location,price,min_stock,is_pack)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (b.code, b.title, b.series, b.volume, b.author, b.publisher,
                                                     b.category, b.type, b.location, b.price, b.min_stock, b.is_pack))
            bid = cur.lastrowid
            db.log_audit(c, get_current_user(request), "INSERT", "book", bid, f"Création livre « {b.title} » ({b.code})", snapshot_after=_dump(b) | {"id": bid})
            return {"id": bid}
        except Exception:
            raise HTTPException(400, "Ce code existe déjà")


@router.put("/{bid}")
def book_upd(bid: int, b: BookIn, request: Request):
    with db.tx() as c:
        old = c.execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone()
        if not old:
            raise HTTPException(404, "Livre introuvable")
        c.execute("""UPDATE books SET code=?,title=?,series=?,volume=?,author=?,publisher=?,category=?,type=?,
            location=?,price=?,min_stock=? WHERE id=?""", (b.code, b.title, b.series, b.volume, b.author,
                                                           b.publisher, b.category, b.type, b.location, b.price, b.min_stock, bid))
        db.log_audit(c, get_current_user(request), "UPDATE", "book", bid, f"Modification fiche « {b.title} »", snapshot_before=dict(old), snapshot_after=_dump(b) | {"id": bid})
    return {"ok": True}


@router.delete("/{bid}")
def book_del(bid: int, request: Request):
    with db.tx() as c:
        old = c.execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone()
        if old:
            c.execute("UPDATE books SET active=0 WHERE id=?", (bid,))
            db.log_audit(c, get_current_user(request), "DELETE", "book", bid, f"Archivage livre « {old['title']} »", snapshot_before=dict(old))
    return {"ok": True}


@router.put("/{bid}/pack")
def pack_set(bid: int, items: List[PackItem], request: Request):
    with db.tx() as c:
        bk = c.execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone()
        old_items = db.rows(c, "SELECT book_id, qty FROM pack_items WHERE pack_id=?", (bid,))
        c.execute("DELETE FROM pack_items WHERE pack_id=?", (bid,))
        for i in items:
            c.execute("INSERT INTO pack_items(pack_id,book_id,qty) VALUES(?,?,?) ON CONFLICT(pack_id,book_id) DO UPDATE SET qty=qty+excluded.qty",
                      (bid, i.book_id, max(1, i.qty)))
        db.log_audit(c, get_current_user(request), "UPDATE", "pack", bid, f"Modification composition pack « {bk['title'] if bk else bid} »",
                     snapshot_before={"items": old_items}, snapshot_after={"items": [_dump(i) for i in items]})
    return {"ok": True}


@router.get("/{bid}/lots")
def lots_by_book(bid: int):
    with db.tx() as c:
        return db.rows(c, f"""SELECT l.*, o.name owner, o.color, o.reverse_pct o_pct, ({db.LOT_REMAINING}) remaining
            FROM lots l JOIN owners o ON o.id=l.owner_id WHERE l.book_id=? ORDER BY l.date DESC""", (bid,))


@router.get("/{bid}/stats")
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


@router.get("/scan/{code}")
def scan_book(code: str):
    clean = code.strip()[:40]
    plain = clean.replace("-", "").replace(" ", "")
    with db.tx() as c:
        book = c.execute("""SELECT * FROM books WHERE active=1 AND
            (code = ? OR REPLACE(REPLACE(code,'-',''),' ','') = ?) LIMIT 1""", (clean, plain)).fetchone()
        if not book:
            raise HTTPException(404, f"Aucun livre pour le code « {clean} »")
        return _mobile_book(c, book)


@router.get("/search")
def search_books(q: str):
    q = q.strip()[:60]
    if len(q) < 2:
        return []
    like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with db.tx() as c:
        rows = c.execute("""SELECT * FROM books WHERE active=1 AND
            (title LIKE ? ESCAPE '\\' OR code LIKE ? ESCAPE '\\' OR author LIKE ? ESCAPE '\\' OR series LIKE ? ESCAPE '\\')
            ORDER BY title LIMIT 8""", (like, like, like, like)).fetchall()
        return [_mobile_book(c, r) for r in rows]
