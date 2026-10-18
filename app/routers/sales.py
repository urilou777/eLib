"""
app/routers/sales.py
-------------------------------------------------------------------------------
Routeur FastAPI dédié aux opérations de caisse, ventes, trésorerie, règlements,
réservations, conformité RGPD et analyses croisées / statistiques.
-------------------------------------------------------------------------------
"""

import re
from datetime import date, timedelta
from typing import Optional, List, Literal
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from .. import db, security

router = APIRouter(prefix="/api", tags=["sales"])

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


def require_known_user(request: Request) -> str:
    u = get_current_user(request)
    if getattr(request.state, "role", "desk") == "mobile":
        with db.tx() as c:
            if not c.execute("SELECT 1 FROM users WHERE name=?", (u,)).fetchone():
                raise HTTPException(400, "Profil libraire inconnu : choisissez votre prénom dans la liste")
    return u


def _broadcast(event_type: str, data: dict):
    from ..main import live_hub
    live_hub.broadcast(event_type, data)


def _remove_basket(device_id: str, action: dict = None):
    from ..main import live_hub
    live_hub.remove_basket(device_id, action=action)


def _get_current_moment() -> str:
    from ..main import get_current_moment
    return get_current_moment()


# ---------- Modèles Pydantic ----------
class AllocIn(BaseModel):
    book_id: Optional[int] = None
    lot_id: int
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


# ---------- Ventes ----------
@router.post("/sales")
def sale_add(s: SaleIn, request: Request):
    user = require_known_user(request)
    
    with db.tx(immediate=True) as c:
        payments_list = [_dump(p) for p in s.payments] if s.payments else None
        sid, warns = db.create_sale(c, s.date, s.payment, s.note, [_dump(l) for l in s.lines],
                                    manual=True, user_name=user,
                                    customer_gender=s.customer_gender,
                                    customer_age_group=s.customer_age_group,
                                    is_star=s.is_star or 0,
                                    service_moment=s.service_moment or _get_current_moment(),
                                    payments=payments_list)
        total = sum((l.unit_price if l.unit_price is not None else
                     c.execute("SELECT price FROM books WHERE id=?", (l.book_id,)).fetchone()["price"]) * l.qty for l in s.lines)
        sale_row = c.execute("SELECT payment FROM sales WHERE id=?", (sid,)).fetchone()
        eff_payment = sale_row["payment"] if sale_row else s.payment
        
        summary_lines = []
        for l in s.lines[:4]:
            brow = c.execute("SELECT title FROM books WHERE id=?", (l.book_id,)).fetchone()
            summary_lines.append(f"{l.qty}× {brow['title'] if brow else 'Livre'}")
        if len(s.lines) > 4:
            summary_lines.append(f"+{len(s.lines) - 4} autre(s)")

        db.log_audit(c, user, "INSERT", "sale", sid,
                     f"Vente #{sid} : {total:.2f} € ({len(s.lines)} article(s), {eff_payment}) par {user}",
                     snapshot_after={"id": sid, "date": s.date, "total": total, "payment": eff_payment,
                                     "payments": payments_list, "user_name": user,
                                     "customer_gender": s.customer_gender, "customer_age_group": s.customer_age_group,
                                     "is_star": s.is_star, "service_moment": s.service_moment, "lines": [_dump(l) for l in s.lines]})
    
    dev = security.device_from_request(request)
    dev_id = str(dev["id"]) if dev else (request.client.host if request.client else "local")
    _remove_basket(dev_id, action={"type": "sale_cleared"})

    _broadcast("sale_registered", {
        "id": sid,
        "date": s.date,
        "total": round(total, 2),
        "qty": sum(l.qty for l in s.lines),
        "user_name": user,
        "payment": eff_payment,
        "service_moment": s.service_moment,
        "customer_gender": s.customer_gender,
        "customer_age_group": s.customer_age_group,
        "is_star": s.is_star or 0,
        "summary": " · ".join(summary_lines)
    })
    _broadcast("metrics_invalidated", {"reason": "sale_added", "sale_id": sid})

    return {"id": sid, "total": total, "warnings": warns}


@router.get("/sales")
def sales(limit: int = 200):
    with db.tx() as c:
        return db.rows(c, """SELECT s.id,s.date,s.payment,s.note,COALESCE(s.user_name,'Anonyme') user_name,
            s.customer_gender, s.customer_age_group, COALESCE(s.is_star, 0) is_star, s.service_moment,
            SUM(l.qty*l.unit_price) total, SUM(l.qty) qty,
            GROUP_CONCAT(l.qty||'× '||b.title, ' · ') detail
            FROM sales s JOIN sale_lines l ON l.sale_id=s.id JOIN books b ON b.id=l.book_id
            GROUP BY s.id ORDER BY s.date DESC, s.id DESC LIMIT ?""", (limit,))


@router.delete("/sales/{sid}")
def sale_del(sid: int, request: Request):
    with db.tx() as c:
        sale = c.execute("SELECT * FROM sales WHERE id=?", (sid,)).fetchone()
        if sale:
            sale_payments = db.rows(c, "SELECT payment, amount FROM sale_payments WHERE sale_id=?", (sid,))
            c.execute("DELETE FROM sales WHERE id=?", (sid,))
            db.log_audit(c, get_current_user(request), "DELETE", "sale", sid,
                         f"Suppression/annulation vente #{sid}",
                         snapshot_before=dict(sale) | {"payments": sale_payments})
    _broadcast("metrics_invalidated", {"reason": "sale_deleted", "sale_id": sid})
    return {"ok": True}


# ---------- Trésorerie & Mouvements ----------
@router.get("/treasury")
def treasury_summary():
    with db.tx() as c:
        sales_by_pay = db.rows(c, """
            SELECT payment, COALESCE(SUM(amount), 0) total, COUNT(DISTINCT sale_id) count
            FROM sale_payments
            GROUP BY payment
        """)
        movements = db.rows(c, "SELECT * FROM cash_movements ORDER BY date DESC, id DESC")
        
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
        
        deposits_cash = c.execute("""
            SELECT COALESCE(SUM(amount), 0) s FROM cash_movements WHERE type = 'DEPOSIT' AND channel = 'ESPECES'
        """).fetchone()["s"]
        
        withdrawals_cash = c.execute("""
            SELECT COALESCE(SUM(amount), 0) s FROM cash_movements WHERE type = 'WITHDRAWAL' AND channel = 'ESPECES'
        """).fetchone()["s"]
        
        cash_in_drawer = sales_cash + deposits_cash - withdrawals_cash

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
        
        users = [u["name"] for u in db.rows(c, "SELECT name FROM users ORDER BY name")]
        extra_users = [r["u"] for r in db.rows(c, "SELECT DISTINCT user_name u FROM sales WHERE user_name IS NOT NULL AND user_name != '' UNION SELECT DISTINCT user_name u FROM cash_movements")]
        all_user_names = sorted(list(set(users + extra_users)))
        
        user_balances = []
        for uname in all_user_names:
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

            wero_received = c.execute("""
                SELECT COALESCE(SUM(sp.amount), 0) s
                FROM sale_payments sp
                JOIN sales s ON s.id = sp.sale_id
                WHERE s.user_name = ? AND (sp.payment LIKE '%Wero%' OR sp.payment LIKE '%perso%')
            """, (uname,)).fetchone()["s"]
            
            cash_received = c.execute("""
                SELECT COALESCE(SUM(sp.amount), 0) s
                FROM sale_payments sp
                JOIN sales s ON s.id = sp.sale_id
                WHERE s.user_name = ? AND sp.payment LIKE '%Espèce%'
            """, (uname,)).fetchone()["s"]
            
            paypal_sales = c.execute("""
                SELECT COALESCE(SUM(sp.amount), 0) s
                FROM sale_payments sp
                JOIN sales s ON s.id = sp.sale_id
                WHERE s.user_name = ? AND (sp.payment = 'CB' OR sp.payment LIKE '%CB%' OR sp.payment LIKE '%PayPal%')
            """, (uname,)).fetchone()["s"]
            
            deposited = c.execute("""
                SELECT COALESCE(SUM(amount), 0) s
                FROM cash_movements
                WHERE user_name = ? AND type = 'DEPOSIT'
            """, (uname,)).fetchone()["s"]
            
            withdrawn = c.execute("""
                SELECT COALESCE(SUM(amount), 0) s
                FROM cash_movements
                WHERE user_name = ? AND type = 'WITHDRAWAL'
            """, (uname,)).fetchone()["s"]
            
            net_to_deposit = icc_wero_received - deposited + withdrawn
            
            user_balances.append({
                "user_name": uname,
                "cr_due_to_paypal": cr_due_to_paypal,
                "icc_wero_received": icc_wero_received,
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
            "cr_paypal_total": cr_paypal_total,
            "cr_non_paypal_total": cr_non_paypal_total,
            "sales_by_pay": sales_by_pay,
            "user_balances": user_balances,
            "movements": movements
        }


@router.post("/treasury/movements")
def cash_movement_add(m: CashMovementIn, request: Request):
    op_user = get_current_user(request)
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


@router.delete("/treasury/movements/{mid}")
def cash_movement_del(mid: int, request: Request):
    op_user = get_current_user(request)
    with db.tx() as c:
        mov = c.execute("SELECT * FROM cash_movements WHERE id=?", (mid,)).fetchone()
        if not mov:
            raise HTTPException(404, "Mouvement introuvable")
        if mov["user_name"] != op_user:
            raise HTTPException(403, f"Opération refusée : seul « {mov['user_name']} » peut modifier ou annuler ses propres opérations")
        c.execute("DELETE FROM cash_movements WHERE id=?", (mid,))
        db.log_audit(c, op_user, "DELETE", "cash_movement", mid,
                     f"Annulation mouvement caisse #{mid} ({mov['user_name']} - {mov['amount']:.2f} €)",
                     snapshot_before=dict(mov))
    return {"ok": True}


# ---------- Règlements / Settlements ----------
@router.get("/settlements")
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


@router.post("/settlements")
def settle(s: SettleIn, request: Request):
    with db.tx() as c:
        cur = c.execute("INSERT INTO settlements(owner_id,date,amount,note) VALUES(?,?,?,?)",
                        (s.owner_id, s.date or date.today().isoformat(), s.amount, s.note))
        sid = cur.lastrowid
        ow = c.execute("SELECT name FROM owners WHERE id=?", (s.owner_id,)).fetchone()
        db.log_audit(c, get_current_user(request), "INSERT", "settlement", sid,
                     f"Règlement {s.amount:.2f} € à « {ow['name'] if ow else s.owner_id} »",
                     snapshot_after=_dump(s) | {"id": sid})
    return {"ok": True}


# ---------- Réservations ----------
@router.get("/reservations")
def res_list():
    with db.tx() as c:
        return db.rows(c, "SELECT * FROM reservations ORDER BY status='Servie', id DESC")


@router.post("/reservations")
def res_add(r: ResIn, request: Request):
    with db.tx() as c:
        cur = c.execute("INSERT INTO reservations(name,phone,title,qty,date,status,note) VALUES(?,?,?,?,?,?,?)",
                        (r.name, r.phone, r.title, r.qty, date.today().isoformat(), r.status, r.note))
        rid = cur.lastrowid
        db.log_audit(c, get_current_user(request), "INSERT", "reservation", rid,
                     f"Réservation pour « {r.name} » : {r.qty}× {r.title}", snapshot_after=_dump(r) | {"id": rid})
    return {"ok": True}


@router.put("/reservations/{rid}")
def res_upd(rid: int, r: ResIn, request: Request):
    with db.tx() as c:
        old = c.execute("SELECT * FROM reservations WHERE id=?", (rid,)).fetchone()
        c.execute("UPDATE reservations SET name=?,phone=?,title=?,qty=?,status=?,note=? WHERE id=?",
                  (r.name, r.phone, r.title, r.qty, r.status, r.note, rid))
        db.log_audit(c, get_current_user(request), "UPDATE", "reservation", rid,
                     f"Mise à jour réservation #{rid} ({r.name}) -> statut: {r.status}",
                     snapshot_before=dict(old) if old else None, snapshot_after=_dump(r) | {"id": rid})
    return {"ok": True}


@router.delete("/reservations/{rid}")
def res_del(rid: int, request: Request):
    with db.tx(immediate=True) as c:
        old = c.execute("SELECT * FROM reservations WHERE id=?", (rid,)).fetchone()
        if old:
            c.execute("DELETE FROM reservations WHERE id=?", (rid,))
            safe_old = dict(old)
            if safe_old.get("phone"):
                safe_old["phone"] = "[MASQUÉ RGPD]"
            db.log_audit(c, get_current_user(request), "DELETE", "reservation", rid,
                         f"Suppression réservation #{rid} ({old['name']})", snapshot_before=safe_old)
    return {"ok": True}


# ---------- Conformité RGPD ----------
@router.get("/gdpr/info")
def gdpr_info():
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


@router.post("/gdpr/cleanup")
def gdpr_cleanup(request: Request, days: int = 90):
    user = get_current_user(request)
    with db.tx(immediate=True) as c:
        count = db.clean_gdpr_reservations(c, days_retention=max(1, days))
        if count > 0:
            db.log_audit(c, user, "UPDATE", "gdpr", None,
                         f"Purge RGPD : anonymisation de {count} réservation(s) de plus de {days} jours")
    return {"ok": True, "anonymized": count, "retention_days": days}


# ---------- Statistiques & Analyses ----------
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


@router.get("/stats")
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
        
        from .books import _books
        low = [b for b in _books(c, "is_pack=0") if b["stock"] <= b["min_stock"]]
        low.sort(key=lambda b: b["stock"])
        since = (date.today() - timedelta(days=30)).isoformat()
        rate = {r["book_id"]: r["q"] / 30 for r in db.rows(c, "SELECT book_id, SUM(qty) q FROM allocations WHERE date>=? GROUP BY book_id", (since,))}
        for b in low:
            b["days_left"] = round(b["stock"] / rate[b["id"]]) if rate.get(b["id"]) else None
        
        pos_sales = c.execute(f"""
            SELECT COUNT(DISTINCT s.id) n, COALESCE(SUM(l.qty * l.unit_price), 0) rev
            FROM sales s
            JOIN sale_lines l ON l.sale_id = s.id
            WHERE {Ws} AND (s.note IS NULL OR s.note != 'Import Excel')
        """, As).fetchone()
        pos_nb = pos_sales["n"] or 0
        pos_rev = pos_sales["rev"] or 0
        pos_avg_basket = (pos_rev / pos_nb) if pos_nb else 0
        avg_book_price = (k["rev"] / k["qty"]) if k["qty"] else 0

        by_gender = db.rows(c, f"""
            SELECT COALESCE(s.customer_gender, 'Non renseigné') label,
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
            SELECT COALESCE(s.customer_age_group, 'Non renseigné') label,
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


@router.get("/stats/matrix")
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
    start = start if (start and re.match(r"^\d{4}-\d{2}-\d{2}$", start)) else "0000-00-00"
    end = end if (end and re.match(r"^\d{4}-\d{2}-\d{2}$", end)) else "9999-12-31"

    row_key = MATRIX_ALIASES.get(row, row)
    if row_key not in MATRIX_DIMENSIONS:
        raise HTTPException(400, f"Dimension ligne invalide : '{row}'. Choix possibles : {list(MATRIX_DIMENSIONS.keys())}")

    col_key = None
    if col and col.strip():
        col_key = MATRIX_ALIASES.get(col.strip(), col.strip())
        if col_key not in MATRIX_DIMENSIONS:
            raise HTTPException(400, f"Dimension colonne invalide : '{col}'. Choix possibles : {list(MATRIX_DIMENSIONS.keys())}")
        if col_key == row_key:
            col_key = None

    row_cfg = MATRIX_DIMENSIONS[row_key]
    col_cfg = MATRIX_DIMENSIONS[col_key] if col_key else None

    filters = ["s.date BETWEEN ? AND ?"]
    params = [start, end]

    if moment:
        filters.append("s.service_moment = ?")
        params.append(moment)
    if age_group:
        filters.append("s.customer_age_group = ?")
        params.append(age_group)
    if gender:
        filters.append("s.customer_gender = ?")
        params.append(gender)
    if is_star is not None and is_star != "":
        try:
            filters.append("s.is_star = ?")
            params.append(int(is_star))
        except ValueError:
            pass
    if payment:
        filters.append("s.payment = ?")
        params.append(payment)
    if category:
        filters.append("b.category = ?")
        params.append(category)

    where_sql = " AND ".join(filters)

    from_sql = """
        FROM sales s
        JOIN sale_lines sl ON sl.sale_id = s.id
        JOIN books b ON b.id = sl.book_id
        LEFT JOIN allocations a ON a.line_id = sl.id
        LEFT JOIN owners o ON o.id = a.owner_id
    """

    with db.tx() as c:
        q_tot = f"""
            SELECT 
                COUNT(DISTINCT s.id) as total_tickets,
                COALESCE(SUM(a.revenue), 0) as total_revenue,
                COALESCE(SUM(a.due), 0) as total_due,
                COALESCE(SUM(a.revenue - a.due), 0) as total_margin,
                COALESCE(SUM(a.qty), 0) as total_qty,
                COUNT(DISTINCT CASE WHEN s.is_star = 1 THEN s.id END) as total_star_tickets,
                COALESCE(SUM(CASE WHEN s.is_star = 1 THEN a.revenue ELSE 0 END), 0) as total_star_revenue
            {from_sql}
            WHERE {where_sql}
        """
        tot = dict(c.execute(q_tot, params).fetchone())
        tot_rev = tot["total_revenue"] or 0
        tot_tickets = tot["total_tickets"] or 0
        tot_qty = tot["total_qty"] or 0
        tot_margin = tot["total_margin"] or 0
        tot_star_rev = tot["total_star_revenue"] or 0

        row_expr = row_cfg["expr"]
        col_expr = col_cfg["expr"] if col_cfg else None

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
                    "col_val": None,
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
