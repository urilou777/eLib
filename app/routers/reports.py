"""Reports API routes."""

from fastapi import APIRouter
import io
import os
import re
import secrets
import shutil
import zipfile
from datetime import date, datetime, timedelta
from fastapi import HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse
from typing import Optional
from .. import db, excel_io
from ..api_common import get_current_user
from ..services import BACKUPS, BACKUP_NAME, MATRIX_ALIASES, MATRIX_DIMENSIONS, MAX_IMPORT_BYTES, MAX_UNZIPPED_BYTES, MIRROR, _books, _dirty, _forecast, backup_path, cleanup_old_backups

router = APIRouter()

@router.get("/api/stats")
def stats(start: Optional[str] = None, end: Optional[str] = None, moment: Optional[str] = None):
    start = start if (start and re.match(r"^\d{4}-\d{2}-\d{2}$", start)) else "0000-00-00"
    end = end if (end and re.match(r"^\d{4}-\d{2}-\d{2}$", end)) else "9999-12-31"
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
        for o in db.rows(c, "SELECT id, name FROM owners"):
            d = db.owner_payable_due(c, o["id"])
            p = c.execute("SELECT COALESCE(SUM(amount),0) s FROM settlements WHERE owner_id=?", (o["id"],)).fetchone()["s"]
            remaining = d - p
            if o["name"].strip().lower() == "cité royale":
                remaining = max(0, remaining)
            due_open += remaining
        monthly = db.rows(c, f"""SELECT strftime('%Y-%m',a.date) m, SUM(revenue) revenue, SUM(due) due, SUM(qty) qty
            FROM allocations a WHERE {W} GROUP BY m ORDER BY m""", A)
        by_owner_month = db.rows(c, f"""SELECT strftime('%Y-%m',a.date) m, COALESCE(o.name,'Sans stock') owner, COALESCE(o.color,'#8892b0') color, SUM(revenue) revenue
            FROM allocations a LEFT JOIN owners o ON o.id=a.owner_id WHERE {W} GROUP BY m,owner ORDER BY m""", A)
        # Série brute par jour et par origine : le frontend regroupe en jour/semaine/mois
        # selon la période choisie (une évolution mensuelle n'a pas de sens sur 1 semaine).
        by_owner_day = db.rows(c, f"""SELECT a.date d, COALESCE(o.name,'Sans stock') owner, COALESCE(o.color,'#8892b0') color, SUM(revenue) revenue
            FROM allocations a LEFT JOIN owners o ON o.id=a.owner_id WHERE {W} GROUP BY d,owner ORDER BY d""", A)
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
                "monthly": monthly, "by_owner_month": by_owner_month, "by_owner_day": by_owner_day, "forecast": fc,
                "daily": daily, "top": top, "by_category": by_cat, "by_publisher": by_pub, "by_owner": by_owner,
                "payments": pay, "weekday": wd, "by_gender": by_gender, "by_age": by_age, "by_star": by_star, "by_moment": by_moment, "low_stock": low[:30]}

@router.get("/api/stats/matrix")
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

@router.post("/api/import")
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

@router.get("/api/export")
def export_xlsx():
    path = os.path.join(db.DATA_DIR, f"Export_{datetime.now():%Y%m%d_%H%M}.xlsx")
    excel_io.export_workbook(path)
    return FileResponse(path, filename=os.path.basename(path),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@router.post("/api/backup")
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

@router.get("/api/backups")
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

@router.get("/api/backups/{filename}/download")
def download_backup(filename: str):
    fpath = backup_path(filename)
    if not os.path.isfile(fpath):
        raise HTTPException(404, "Fichier de sauvegarde introuvable")
    return FileResponse(fpath, filename=filename)

@router.delete("/api/backups/{filename}")
def delete_backup_file(filename: str, request: Request):
    fpath = backup_path(filename)
    if not os.path.isfile(fpath):
        raise HTTPException(404, "Fichier introuvable")
    os.remove(fpath)
    with db.tx() as c:
        db.log_audit(c, get_current_user(request), "DELETE", "backup", None, f"Suppression fichier de sauvegarde « {filename} »")
    return {"ok": True}

@router.post("/api/backups/cleanup")
def trigger_backup_cleanup(request: Request):
    """Purge immédiate des snapshots horaires et fichiers temporaires obsolètes selon les règles de rétention."""
    purged = cleanup_old_backups()
    with db.tx() as c:
        db.log_audit(c, get_current_user(request), "CLEANUP", "backup", None, f"Purge et rétention des sauvegardes ({purged} fichiers nettoyés)")
    return {"ok": True, "purged": purged}

@router.post("/api/backups/{filename}/restore")
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

@router.get("/api/info")
def info():
    """Chemins locaux : réservé au poste de caisse (non listé dans la politique d'accès des téléphones)."""
    return {"data_dir": db.DATA_DIR, "mirror": MIRROR, "backups": BACKUPS}

@router.get("/api/system/health")
def system_health():
    """Télémétrie et état de santé du système local :
    Espace disque, taille de la base SQLite et WAL, intégrité, nombre de sauvegardes."""
    total, used, free = shutil.disk_usage(db.DATA_DIR)
    db_size = os.path.getsize(db.DB_PATH) if os.path.exists(db.DB_PATH) else 0
    wal_path = db.DB_PATH + "-wal"
    wal_size = os.path.getsize(wal_path) if os.path.exists(wal_path) else 0
    backup_files = [f for f in os.listdir(BACKUPS) if f.endswith((".db", ".xlsx"))] if os.path.exists(BACKUPS) else []

    integrity_ok = True
    try:
        with db.tx() as c:
            row = c.execute("PRAGMA quick_check").fetchone()
            integrity_ok = bool(row and row[0] == "ok")
    except Exception:
        integrity_ok = False

    return {
        "status": "optimal" if (integrity_ok and free > 1024 * 1024 * 500) else "warning",
        "integrity": "ok" if integrity_ok else "corrupted",
        "disk": {
            "total_gb": round(total / (1024 ** 3), 2),
            "free_gb": round(free / (1024 ** 3), 2),
            "used_gb": round(used / (1024 ** 3), 2),
            "percent_free": round((free / total) * 100, 1)
        },
        "database": {
            "db_size_mb": round(db_size / (1024 ** 2), 2),
            "wal_size_mb": round(wal_size / (1024 ** 2), 2),
            "mode": "WAL"
        },
        "backups": {
            "count": len(backup_files)
        }
    }
