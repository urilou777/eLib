"""Inventory API routes."""

from fastapi import APIRouter
from datetime import date, timedelta
from fastapi import HTTPException, Request
from typing import List
from .. import db
from ..api_common import dump_model as _dump, get_current_user
from ..realtime import live_hub
from ..schemas import AdjIn, LotIn, PackItem
from .admin import owners

router = APIRouter()

@router.put("/api/books/{bid}/pack")
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

@router.get("/api/books/{bid}/lots")
def lots(bid: int):
    with db.tx() as c:
        return db.rows(c, f"""SELECT l.*, o.name owner, o.color, o.reverse_pct o_pct, ({db.LOT_REMAINING}) remaining
            FROM lots l JOIN owners o ON o.id=l.owner_id WHERE l.book_id=? ORDER BY l.date DESC""", (bid,))

@router.get("/api/books/{bid}/stats")
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

@router.post("/api/lots")
def lot_add(l: LotIn, request: Request):
    user = get_current_user(request)
    with db.tx() as c:
        cur = c.execute("INSERT INTO lots(book_id,owner_id,date,qty_in,unit_cost,reverse_pct,note) VALUES(?,?,?,?,?,?,?)",
                        (l.book_id, l.owner_id, l.date or date.today().isoformat(), l.qty_in, l.unit_cost, l.reverse_pct, l.note))
        lid = cur.lastrowid
        bk = c.execute("SELECT title FROM books WHERE id=?", (l.book_id,)).fetchone()
        ow = c.execute("SELECT name FROM owners WHERE id=?", (l.owner_id,)).fetchone()
        db.log_audit(c, user, "INSERT", "lot", lid,
                     f"Entrée stock : {l.qty_in}× « {bk['title'] if bk else l.book_id} » ({ow['name'] if ow else l.owner_id})",
                     snapshot_after=_dump(l) | {"id": lid})
    live_hub.broadcast("activity_logged", {
        "type": "stock_added",
        "user_name": user,
        "title": bk["title"] if bk else f"Livre #{l.book_id}",
        "detail": f"+{l.qty_in} ex. ({ow['name'] if ow else 'Rayon'})",
        "data": {"book_id": l.book_id, "qty": l.qty_in}
    })
    live_hub.broadcast("metrics_invalidated", {"reason": "stock_updated"})
    return {"ok": True}

@router.post("/api/lots/{lid}/adjust")
def lot_adjust(lid: int, a: AdjIn, request: Request):
    user = get_current_user(request)
    with db.tx() as c:
        lot = c.execute("SELECT * FROM lots WHERE id=?", (lid,)).fetchone()
        bk = c.execute("SELECT title FROM books WHERE id=?", (lot['book_id'],)).fetchone() if lot else None
        cur = c.execute("INSERT INTO adjustments(lot_id,date,delta,reason) VALUES(?,?,?,?)",
                        (lid, a.date or date.today().isoformat(), a.delta, a.reason))
        jid = cur.lastrowid
        db.log_audit(c, user, "INSERT", "adjustment", jid,
                     f"Ajustement stock ({'+' if a.delta > 0 else ''}{a.delta}) « {bk['title'] if bk else ''} » : {a.reason}",
                     snapshot_after={"id": jid, "lot_id": lid, "delta": a.delta, "reason": a.reason})
    live_hub.broadcast("activity_logged", {
        "type": "stock_adjusted",
        "user_name": user,
        "title": bk["title"] if bk else "Livre",
        "detail": f"Ajustement {'+' if a.delta > 0 else ''}{a.delta} ({a.reason})",
        "data": {"lot_id": lid, "delta": a.delta}
    })
    live_hub.broadcast("metrics_invalidated", {"reason": "stock_updated"})
    return {"ok": True}
