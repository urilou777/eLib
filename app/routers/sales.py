"""Sales API routes."""

from fastapi import APIRouter
from datetime import date
from fastapi import HTTPException, Request
from .. import db, security
from ..api_common import dump_model as _dump, get_current_user, require_known_user
from ..realtime import live_hub
from ..schemas import CashMovementIn, ResIn, SaleIn, SettleIn
from ..services import get_current_moment

router = APIRouter()

@router.post("/api/sales")
def sale_add(s: SaleIn, request: Request):
    user = require_known_user(request)

    with db.tx(immediate=True) as c:
        payments_list = [_dump(p) for p in s.payments] if s.payments else None
        sid, warns = db.create_sale(c, s.date, s.payment, s.note, [_dump(l) for l in s.lines],
                                    manual=True, user_name=user,
                                    customer_gender=s.customer_gender,
                                    customer_age_group=s.customer_age_group,
                                    is_star=s.is_star or 0,
                                    service_moment=s.service_moment or get_current_moment(),
                                    payments=payments_list)
        total = sum((l.unit_price if l.unit_price is not None else
                     c.execute("SELECT price FROM books WHERE id=?", (l.book_id,)).fetchone()["price"]) * l.qty for l in s.lines)
        sale_row = c.execute("SELECT payment FROM sales WHERE id=?", (sid,)).fetchone()
        eff_payment = sale_row["payment"] if sale_row else s.payment
        # Livres pour le flux live
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

    # Nettoyer l'éventuel panier actif du terminal ayant validé
    dev = security.device_from_request(request)
    dev_id = str(dev["id"]) if dev else (request.client.host if request.client else "local")
    live_hub.remove_basket(dev_id, action={"type": "sale_cleared"})

    # Diffuser l'événement en direct pour la régie CCTV et l'invalidation des métriques
    live_hub.broadcast("sale_registered", {
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
    live_hub.broadcast("metrics_invalidated", {"reason": "sale_added", "sale_id": sid})

    return {"id": sid, "total": total, "warnings": warns}

@router.get("/api/sales")
def sales(limit: int = 200):
    with db.tx() as c:
        return db.rows(c, """SELECT s.id,s.date,s.payment,s.note,COALESCE(s.user_name,'Anonyme') user_name,
            s.customer_gender, s.customer_age_group, COALESCE(s.is_star, 0) is_star, s.service_moment,
            SUM(l.qty*l.unit_price) total, SUM(l.qty) qty,
            GROUP_CONCAT(l.qty||'× '||b.title, ' · ') detail
            FROM sales s JOIN sale_lines l ON l.sale_id=s.id JOIN books b ON b.id=l.book_id
            GROUP BY s.id ORDER BY s.date DESC, s.id DESC LIMIT ?""", (limit,))

@router.delete("/api/sales/{sid}")
def sale_del(sid: int, request: Request):
    with db.tx() as c:
        sale = c.execute("SELECT * FROM sales WHERE id=?", (sid,)).fetchone()
        if sale:
            sale_payments = db.rows(c, "SELECT payment, amount FROM sale_payments WHERE sale_id=?", (sid,))
            c.execute("DELETE FROM sales WHERE id=?", (sid,))
            db.log_audit(c, get_current_user(request), "DELETE", "sale", sid,
                         f"Suppression/annulation vente #{sid}",
                         snapshot_before=dict(sale) | {"payments": sale_payments})
    live_hub.broadcast("metrics_invalidated", {"reason": "sale_deleted", "sale_id": sid})
    return {"ok": True}

@router.get("/api/treasury")
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

@router.post("/api/treasury/movements")
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

@router.delete("/api/treasury/movements/{mid}")
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

@router.get("/api/settlements")
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

@router.post("/api/settlements")
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

@router.get("/api/reservations")
def res_list():
    with db.tx() as c:
        return db.rows(c, "SELECT * FROM reservations ORDER BY status='Servie', id DESC")

@router.post("/api/reservations")
def res_add(r: ResIn, request: Request):
    with db.tx() as c:
        cur = c.execute("INSERT INTO reservations(name,phone,title,qty,date,status,note) VALUES(?,?,?,?,?,?,?)",
                        (r.name, r.phone, r.title, r.qty, date.today().isoformat(), r.status, r.note))
        rid = cur.lastrowid
        db.log_audit(c, get_current_user(request), "INSERT", "reservation", rid,
                     f"Réservation pour « {r.name} » : {r.qty}× {r.title}", snapshot_after=_dump(r) | {"id": rid})
    return {"ok": True}

@router.put("/api/reservations/{rid}")
def res_upd(rid: int, r: ResIn, request: Request):
    with db.tx() as c:
        old = c.execute("SELECT * FROM reservations WHERE id=?", (rid,)).fetchone()
        c.execute("UPDATE reservations SET name=?,phone=?,title=?,qty=?,status=?,note=? WHERE id=?",
                  (r.name, r.phone, r.title, r.qty, r.status, r.note, rid))
        db.log_audit(c, get_current_user(request), "UPDATE", "reservation", rid,
                     f"Mise à jour réservation #{rid} ({r.name}) -> statut: {r.status}",
                     snapshot_before=dict(old) if old else None, snapshot_after=_dump(r) | {"id": rid})
    return {"ok": True}

@router.delete("/api/reservations/{rid}")
def res_del(rid: int, request: Request):
    with db.tx(immediate=True) as c:
        old = c.execute("SELECT * FROM reservations WHERE id=?", (rid,)).fetchone()
        if old:
            c.execute("DELETE FROM reservations WHERE id=?", (rid,))
            # RGPD Art. 17 (Droit à l'effacement) : anonymiser les données personnelles sensibles du journal d'audit
            safe_old = dict(old)
            if safe_old.get("phone"):
                safe_old["phone"] = "[MASQUÉ RGPD]"
            db.log_audit(c, get_current_user(request), "DELETE", "reservation", rid,
                         f"Suppression réservation #{rid} ({old['name']})", snapshot_before=safe_old)
    return {"ok": True}
