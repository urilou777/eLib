#!/usr/bin/env python3
"""
tools/repair_sales_gui.py
------------------------------------------------------------------------
Outil autonome et éphémère avec interface graphique (GUI) locale
pour la scission et la correction des ventes historiques compressées.

Cet outil est 100% indépendant de l'application de production.
Une fois vos données corrigées, vous pouvez simplement fermer ce script.
------------------------------------------------------------------------
Lancement :
    python tools/repair_sales_gui.py
Accès :
    http://127.0.0.1:8769
"""

import sys
import os
import json
import sqlite3
import shutil
import webbrowser
import threading
from datetime import datetime, date
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Chemin de la base de données SQLite
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "librairie.db")
BACKUP_DIR = os.path.join(DATA_DIR, "sauvegardes")
os.makedirs(BACKUP_DIR, exist_ok=True)

PORT = 8769


def get_db():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Base de données introuvable : {DB_PATH}")
    c = sqlite3.connect(DB_PATH, timeout=30.0)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA journal_mode = WAL")
    c.execute("PRAGMA busy_timeout = 15000")
    return c


def create_pre_backup(prefix="split"):
    """Crée une sauvegarde horodatée avant toute action de scission."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = os.path.join(BACKUP_DIR, f"librairie_backup_{prefix}_{ts}.db")
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(target)
    with dst:
        src.backup(dst, pages=100)
    dst.close()
    src.close()
    return target


# ==============================================================================
# LOGIQUE MÉTIER DE SCISSION ATOMIQUE
# ==============================================================================

def execute_split(sale_id: int, baskets_data: list):
    """
    Exécute la scission atomique d'une vente en N paniers distincts.
    Garantit l'intégrité absolue des stocks, des lignes et des allocations.
    """
    backup_file = create_pre_backup(f"pre_split_sale_{sale_id}")

    conn = get_db()
    try:
        with conn:
            cur = conn.cursor()
            
            # 1. Vérification de la vente d'origine
            orig_sale = cur.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
            if not orig_sale:
                raise ValueError(f"Vente #{sale_id} introuvable.")

            # Récupérer les lignes existantes
            orig_lines = cur.execute("""
                SELECT sl.id, sl.sale_id, sl.book_id, sl.qty, sl.unit_price, b.title
                FROM sale_lines sl
                JOIN books b ON b.id = sl.book_id
                WHERE sl.sale_id = ?
            """, (sale_id,)).fetchall()
            
            orig_lines_map = {l["id"]: dict(l) for l in orig_lines}
            if not orig_lines_map:
                raise ValueError("Cette vente ne contient aucune ligne.")

            # 2. Validation stricte de la répartition
            # Pour chaque ligne, la somme des quantités réparties doit être égale à la quantité d'origine
            allocated_line_qtys = {lid: 0 for lid in orig_lines_map}
            
            for b_idx, b in enumerate(baskets_data):
                for it in b.get("items", []):
                    lid = it["line_id"]
                    qty = int(it["qty"])
                    if lid not in orig_lines_map:
                        raise ValueError(f"La ligne #{lid} n'appartient pas à la vente #{sale_id}.")
                    if qty < 0:
                        raise ValueError(f"Quantité négative interdite sur la ligne #{lid}.")
                    allocated_line_qtys[lid] += qty

            for lid, tot_q in allocated_line_qtys.items():
                orig_q = orig_lines_map[lid]["qty"]
                if tot_q != orig_q:
                    raise ValueError(
                        f"Quantité non équilibrée pour « {orig_lines_map[lid]['title']} » : "
                        f"{tot_q} réparti(s) au lieu de {orig_q}."
                    )

            # 3. Récupérer toutes les allocations existantes pour les lignes de cette vente
            allocs = cur.execute("""
                SELECT a.id, a.line_id, a.book_id, a.lot_id, a.owner_id, a.qty, a.revenue, a.due, a.date
                FROM allocations a
                JOIN sale_lines sl ON sl.id = a.line_id
                WHERE sl.sale_id = ?
                ORDER BY a.id ASC
            """, (sale_id,)).fetchall()

            # Pool d'allocations par line_id
            alloc_pool = {}
            for al in allocs:
                lid = al["line_id"]
                if lid not in alloc_pool:
                    alloc_pool[lid] = []
                alloc_pool[lid].append(dict(al))

            # 4. Nettoyer les anciennes allocations, lignes et paiements de la vente d'origine
            cur.execute("""
                DELETE FROM allocations WHERE line_id IN (
                    SELECT id FROM sale_lines WHERE sale_id = ?
                )
            """, (sale_id,))
            cur.execute("DELETE FROM sale_lines WHERE sale_id = ?", (sale_id,))
            cur.execute("DELETE FROM sale_payments WHERE sale_id = ?", (sale_id,))

            # 5. Reconstruire chaque panier
            created_sales = []
            
            for b_idx, b in enumerate(baskets_data):
                is_orig = bool(b.get("is_original", False))
                b_date = b.get("date") or orig_sale["date"]
                b_pay = b.get("payment") or orig_sale["payment"] or "Espèces"
                b_gender = b.get("customer_gender") or None
                b_age = b.get("customer_age_group") or None
                b_star = int(bool(b.get("is_star", 0)))
                b_moment = b.get("service_moment") or None
                b_user = b.get("user_name") or orig_sale["user_name"] or "Anonyme"
                b_note = b.get("note") or f"Scission vente #{sale_id} (Panier {b_idx + 1})"

                if is_orig:
                    target_sale_id = sale_id
                    # Mise à jour des métadonnées de la vente d'origine
                    cur.execute("""
                        UPDATE sales SET
                            date = ?, payment = ?, user_name = ?,
                            customer_gender = ?, customer_age_group = ?,
                            is_star = ?, service_moment = ?, note = ?
                        WHERE id = ?
                    """, (b_date, b_pay, b_user, b_gender, b_age, b_star, b_moment, b_note, target_sale_id))
                else:
                    # Création d'une nouvelle vente
                    cur.execute("""
                        INSERT INTO sales (date, payment, user_name, customer_gender, customer_age_group, is_star, service_moment, note)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (b_date, b_pay, b_user, b_gender, b_age, b_star, b_moment, b_note))
                    target_sale_id = cur.lastrowid
                    created_sales.append(target_sale_id)

                basket_total = 0.0

                # Traiter chaque article de ce panier
                for it in b.get("items", []):
                    lid = it["line_id"]
                    qty_for_basket = int(it["qty"])
                    if qty_for_basket <= 0:
                        continue

                    orig_l = orig_lines_map[lid]
                    price = float(orig_l["unit_price"])
                    book_id = orig_l["book_id"]
                    basket_total += qty_for_basket * price

                    # Insérer la ligne pour ce panier
                    cur.execute("""
                        INSERT INTO sale_lines (sale_id, book_id, qty, unit_price)
                        VALUES (?, ?, ?, ?)
                    """, (target_sale_id, book_id, qty_for_basket, price))
                    new_line_id = cur.lastrowid

                    # Imputer les allocations correspondantes depuis le pool
                    needed_alloc_qty = qty_for_basket
                    pool = alloc_pool.get(lid, [])
                    
                    while needed_alloc_qty > 0 and pool:
                        al = pool[0]
                        avail_in_al = al["qty"]
                        
                        if avail_in_al <= needed_alloc_qty:
                            # Consommer toute cette allocation
                            take_q = avail_in_al
                            al_rev = al["revenue"]
                            al_due = al["due"]
                            pool.pop(0)
                        else:
                            # Consommer une fraction de cette allocation
                            take_q = needed_alloc_qty
                            unit_rev = al["revenue"] / avail_in_al
                            unit_due = al["due"] / avail_in_al
                            al_rev = take_q * unit_rev
                            al_due = take_q * unit_due
                            # Réduire ce qui reste dans l'allocation source
                            al["qty"] -= take_q
                            al["revenue"] -= al_rev
                            al["due"] -= al_due

                        # Assigner l'allocation à new_line_id
                        cur.execute("""
                            INSERT INTO allocations (line_id, book_id, lot_id, owner_id, qty, revenue, due, date)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (new_line_id, al["book_id"], al["lot_id"], al["owner_id"], take_q, al_rev, al_due, b_date))

                        needed_alloc_qty -= take_q

                # Mettre à jour sale_payments pour cette vente
                cur.execute("""
                    INSERT INTO sale_payments (sale_id, payment, amount)
                    VALUES (?, ?, ?)
                """, (target_sale_id, b_pay, basket_total))

            # 6. Journalisation dans l'audit trail
            cur.execute("""
                INSERT INTO audit_logs (timestamp, user_name, action, target_type, target_id, summary, snapshot_before, snapshot_after)
                VALUES (?, ?, 'SPLIT_SALE', 'sale', ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                "Outil de Réparation",
                sale_id,
                f"Scission de la vente #{sale_id} en {len(baskets_data)} paniers distincts (Nouvelles ventes : {created_sales})",
                json.dumps(dict(orig_sale)),
                json.dumps({"created_sales": created_sales, "baskets": baskets_data})
            ))

        conn.close()
        return {
            "ok": True,
            "created_sales": created_sales,
            "backup_file": backup_file,
            "message": f"Scission réussie ! Vente #{sale_id} scindée en {len(baskets_data)} ventes."
        }

    except Exception as e:
        conn.close()
        raise e


# ==============================================================================
# SERVEUR HTTP & API REST EMBARQUÉE
# ==============================================================================

class SalesRepairHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_content):
        body = html_content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        url = urlparse(self.path)
        path = url.path.rstrip("/")

        if path == "" or path == "/index.html":
            self._send_html(INDEX_HTML)
            return

        conn = get_db()
        try:
            if path == "/api/sales":
                sales = conn.execute("""
                    SELECT s.id, s.date, s.payment, s.user_name, s.customer_gender,
                           s.customer_age_group, s.is_star, s.service_moment, s.note,
                           COUNT(sl.id) as line_count,
                           COALESCE(SUM(sl.qty), 0) as total_qty,
                           COALESCE(SUM(sl.qty * sl.unit_price), 0) as total_rev
                    FROM sales s
                    LEFT JOIN sale_lines sl ON sl.sale_id = s.id
                    GROUP BY s.id
                    ORDER BY s.id ASC
                """).fetchall()
                
                res = []
                for s in sales:
                    item = dict(s)
                    item["is_compressed"] = (item["total_qty"] > 1 or item["line_count"] > 1 or item["note"] == "Import Excel")
                    res.append(item)
                self._send_json({"ok": True, "sales": res})

            elif path.startswith("/api/sales/"):
                sale_id = int(path.split("/")[3])
                sale = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
                if not sale:
                    self._send_json({"ok": False, "error": "Vente non trouvée"}, 404)
                    return
                
                lines = conn.execute("""
                    SELECT sl.id, sl.sale_id, sl.book_id, sl.qty, sl.unit_price,
                           b.code, b.title, b.author, b.publisher, b.price as catalog_price, b.is_pack
                    FROM sale_lines sl
                    JOIN books b ON b.id = sl.book_id
                    WHERE sl.sale_id = ?
                    ORDER BY sl.id ASC
                """, (sale_id,)).fetchall()

                allocs = conn.execute("""
                    SELECT a.id, a.line_id, a.book_id, a.lot_id, a.owner_id, o.name as owner_name,
                           a.qty, a.revenue, a.due, a.date
                    FROM allocations a
                    JOIN sale_lines sl ON sl.id = a.line_id
                    JOIN owners o ON o.id = a.owner_id
                    WHERE sl.sale_id = ?
                    ORDER BY a.id ASC
                """, (sale_id,)).fetchall()

                payments = conn.execute("SELECT * FROM sale_payments WHERE sale_id = ?", (sale_id,)).fetchall()

                lines_res = []
                for l in lines:
                    ld = dict(l)
                    ld["total_price"] = round(ld["qty"] * ld["unit_price"], 2)
                    ld["allocations"] = [dict(a) for a in allocs if a["line_id"] == l["id"]]
                    lines_res.append(ld)

                self._send_json({
                    "ok": True,
                    "sale": dict(sale),
                    "lines": lines_res,
                    "payments": [dict(p) for p in payments]
                })

            elif path == "/api/options":
                owners = conn.execute("SELECT id, name FROM owners ORDER BY priority").fetchall()
                self._send_json({
                    "ok": True,
                    "owners": [dict(o) for o in owners],
                    "payments": ["Espèces", "CB", "Wero", "Virement", "Don"],
                    "genders": ["Femme", "Homme", "Couple"],
                    "ages": ["Enfant / Ado", "Jeune adulte", "Adulte", "Senior"],
                    "moments": ["1er Culte", "2e Culte", "Culte Unique", "Séminaire / Soirée"]
                })

            elif path == "/api/books":
                books = conn.execute("""
                    SELECT b.id, b.code, b.title, b.author, b.publisher, b.category, b.type,
                           b.price, b.is_pack,
                           (SELECT COALESCE(SUM(sl.qty), 0) FROM sale_lines sl WHERE sl.book_id = b.id) as sales_count,
                           COALESCE((SELECT SUM(l.qty_in - COALESCE((SELECT SUM(a.qty) FROM allocations a WHERE a.lot_id=l.id), 0)) FROM lots l WHERE l.book_id=b.id), 0) as stock_est
                    FROM books b
                    ORDER BY b.title COLLATE NOCASE ASC
                """).fetchall()

                res = []
                for b in books:
                    item = dict(b)
                    code = (item["code"] or "").strip()
                    item["is_placeholder"] = bool(
                        (not code) or
                        code.upper().startswith(("NA-", "ICCREN-", "AUTO-", "DUMMY-", "TEMP-")) or
                        (len(code) < 10 and not item["is_pack"])
                    )
                    res.append(item)

                self._send_json({"ok": True, "books": res})

            else:
                self._send_json({"error": "Endpoint introuvable"}, 404)
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, 500)
        finally:
            conn.close()

    def do_POST(self):
        url = urlparse(self.path)
        path = url.path.rstrip("/")
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        conn = get_db()
        try:
            if path == "/api/backup":
                b_file = create_pre_backup("manual")
                self._send_json({"ok": True, "file": b_file, "message": "Sauvegarde créée avec succès."})

            elif path.endswith("/update") and path.startswith("/api/sales/"):
                sale_id = int(path.split("/")[3])
                create_pre_backup(f"pre_update_{sale_id}")
                
                with conn:
                    conn.execute("""
                        UPDATE sales SET
                            date = ?, payment = ?, customer_gender = ?,
                            customer_age_group = ?, is_star = ?, service_moment = ?,
                            user_name = ?, note = ?
                        WHERE id = ?
                    """, (
                        data.get("date"),
                        data.get("payment", "Espèces"),
                        data.get("customer_gender") or None,
                        data.get("customer_age_group") or None,
                        int(bool(data.get("is_star", 0))),
                        data.get("service_moment") or None,
                        data.get("user_name", "Anonyme"),
                        data.get("note") or None,
                        sale_id
                    ))
                    # Mettre à jour sale_payments si présent
                    tot = conn.execute("SELECT SUM(qty * unit_price) FROM sale_lines WHERE sale_id = ?", (sale_id,)).fetchone()[0] or 0.0
                    conn.execute("DELETE FROM sale_payments WHERE sale_id = ?", (sale_id,))
                    conn.execute("INSERT INTO sale_payments(sale_id, payment, amount) VALUES(?, ?, ?)",
                                 (sale_id, data.get("payment", "Espèces"), float(tot)))

                self._send_json({"ok": True, "message": f"Vente #{sale_id} mise à jour avec succès !"})

            elif path.endswith("/split") and path.startswith("/api/sales/"):
                sale_id = int(path.split("/")[3])
                baskets = data.get("baskets", [])
                if len(baskets) < 2:
                    self._send_json({"ok": False, "error": "Il faut au minimum 2 paniers pour scinder une vente."}, 400)
                    return
                
                res = execute_split(sale_id, baskets)
                self._send_json(res)

            elif path.startswith("/api/books/") and path.endswith("/barcode"):
                book_id = int(path.split("/")[3])
                new_code = (data.get("code") or "").strip()
                if not new_code:
                    self._send_json({"ok": False, "error": "Le code-barres ne peut pas être vide."}, 400)
                    return

                # Validation unicité
                dup = conn.execute("SELECT id, title FROM books WHERE code = ? AND id != ?", (new_code, book_id)).fetchone()
                if dup:
                    self._send_json({
                        "ok": False,
                        "error": f"Le code « {new_code} » est déjà utilisé par « {dup['title']} » (Livre #{dup['id']})."
                    }, 400)
                    return

                old_book = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
                if not old_book:
                    self._send_json({"ok": False, "error": f"Livre #{book_id} introuvable."}, 404)
                    return

                b_file = create_pre_backup(f"pre_barcode_book_{book_id}")

                with conn:
                    conn.execute("UPDATE books SET code = ? WHERE id = ?", (new_code, book_id))
                    conn.execute("""
                        INSERT INTO audit_logs (timestamp, user_name, action, target_type, target_id, summary, snapshot_before, snapshot_after)
                        VALUES (?, ?, 'UPDATE_BARCODE', 'book', ?, ?, ?, ?)
                    """, (
                        datetime.now().isoformat(),
                        "Atelier Scission / Codes-barres",
                        book_id,
                        f"Attribution code-barres pour « {old_book['title']} » : « {old_book['code']} » → « {new_code} »",
                        json.dumps(dict(old_book)),
                        json.dumps({"id": book_id, "title": old_book["title"], "code": new_code})
                    ))

                self._send_json({
                    "ok": True,
                    "book_id": book_id,
                    "new_code": new_code,
                    "backup_file": b_file,
                    "message": f"Code-barres enregistré : « {new_code} » pour « {old_book['title']} »"
                })

            else:
                self._send_json({"error": "Endpoint introuvable"}, 404)
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, 500)
        finally:
            conn.close()


# ==============================================================================
# INTERFACE WEB EMBARQUÉE (HTML5 + CSS MODERNE + JAVASCRIPT)
# ==============================================================================

INDEX_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Atelier de Scission & Réparation des Ventes · eLib</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@500;600;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #0b0d13;
  --panel: #131722;
  --panel2: #1a202e;
  --card: #202738;
  --line: rgba(255,255,255,0.08);
  --line-strong: rgba(255,255,255,0.16);
  --text: #e2e8f0;
  --mut: #94a3b8;
  --pri: #6366f1;
  --pri-glow: rgba(99,102,241,0.25);
  --good: #10b981;
  --warn: #f59e0b;
  --bad: #ef4444;
  --cr: #f59e0b;
  --icc: #a855f7;
  --font: 'Plus Jakarta Sans', system-ui, sans-serif;
  --font-h: 'Outfit', system-ui, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  font-size: 13.5px;
  line-height: 1.4;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}
header.top {
  background: var(--panel);
  border-bottom: 1px solid var(--line);
  padding: 12px 24px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  position: sticky;
  top: 0;
  z-index: 50;
}
.brand { display: flex; align-items: center; gap: 12px; }
.brand h1 { font-family: var(--font-h); font-size: 17px; font-weight: 700; color: #fff; letter-spacing: -0.3px; }
.badge-ephemere {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 999px;
  padding: 3px 9px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
}
.btn {
  background: var(--card);
  color: var(--text);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 7px 14px;
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all 0.15s ease;
}
.btn:hover { background: var(--line-strong); border-color: rgba(255,255,255,0.25); }
.btn.pri { background: var(--pri); border-color: var(--pri); color: #fff; box-shadow: 0 0 12px var(--pri-glow); }
.btn.pri:hover { filter: brightness(1.1); }
.btn.good { background: var(--good); border-color: var(--good); color: #fff; }
.btn.sm { padding: 4px 8px; font-size: 11.5px; border-radius: 6px; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; filter: none; }

.layout {
  display: grid;
  grid-template-columns: 340px 1fr;
  flex: 1;
  min-height: 0;
}
aside.sidebar {
  background: var(--panel);
  border-right: 1px solid var(--line);
  padding: 16px;
  overflow-y: auto;
  max-height: calc(100vh - 57px);
}
.sidebar-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--mut);
  margin-bottom: 12px;
  display: flex;
  justify-content: space-between;
}
.sales-list { display: flex; flex-direction: column; gap: 6px; }
.sale-item {
  background: var(--panel2);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
  transition: all 0.15s ease;
  position: relative;
}
.sale-item:hover { background: var(--card); border-color: var(--line-strong); }
.sale-item.active {
  background: rgba(99,102,241,0.12);
  border-color: var(--pri);
  box-shadow: 0 0 12px var(--pri-glow);
}
.sale-item .top-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.sale-id { font-family: var(--font-h); font-weight: 800; font-size: 14px; color: #fff; }
.sale-total { font-family: var(--font-h); font-weight: 700; font-size: 14px; color: var(--good); }
.sale-sub { font-size: 11px; color: var(--mut); display: flex; gap: 8px; align-items: center; }
.tag-compressed {
  background: rgba(245,158,11,0.15);
  color: var(--warn);
  border: 1px solid rgba(245,158,11,0.3);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
}
.tag-qual {
  background: rgba(16,185,129,0.15);
  color: var(--good);
  border: 1px solid rgba(16,185,129,0.3);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
}

main.workspace {
  padding: 24px;
  overflow-y: auto;
  max-height: calc(100vh - 57px);
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.empty-state {
  text-align: center;
  padding: 80px 20px;
  color: var(--mut);
}
.empty-state svg { width: 48px; height: 48px; stroke: var(--mut); margin-bottom: 12px; opacity: 0.5; }

/* En-tête de vente sélectionnée */
.sale-banner {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 16px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.sale-banner h2 { font-family: var(--font-h); font-size: 20px; font-weight: 800; color: #fff; margin-bottom: 2px; }

/* Onglets d'action */
.tabs { display: flex; gap: 8px; border-bottom: 1px solid var(--line); padding-bottom: 8px; }
.tab-btn {
  background: transparent;
  color: var(--mut);
  border: none;
  font-family: inherit;
  font-size: 13.5px;
  font-weight: 700;
  padding: 6px 14px;
  border-radius: 8px;
  cursor: pointer;
}
.tab-btn.active { background: var(--panel2); color: #fff; border: 1px solid var(--line-strong); }

/* Zone des Paniers */
.baskets-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
  gap: 16px;
}
.basket-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.basket-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--line);
  padding-bottom: 10px;
}
.basket-title { font-family: var(--font-h); font-size: 16px; font-weight: 800; color: #fff; }
.basket-total-pill {
  background: rgba(16,185,129,0.15);
  color: var(--good);
  border: 1px solid rgba(16,185,129,0.3);
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 13px;
  font-weight: 800;
}

/* Formulaire Profil dans chaque panier */
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.form-group { display: flex; flex-direction: column; gap: 4px; }
.form-group label { font-size: 11px; font-weight: 700; color: var(--mut); text-transform: uppercase; }
.select-input, .text-input {
  background: var(--panel2);
  border: 1px solid var(--line);
  border-radius: 7px;
  padding: 6px 10px;
  color: var(--text);
  font-family: inherit;
  font-size: 12px;
  outline: none;
}
.select-input:focus, .text-input:focus { border-color: var(--pri); }

/* Puces rapides profil */
.chip-row { display: flex; gap: 4px; flex-wrap: wrap; }
.p-chip {
  background: var(--panel2);
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}
.p-chip.on { background: var(--pri); border-color: var(--pri); color: #fff; }
.p-chip.star-on { background: #d97706; border-color: #f59e0b; color: #fff; }

/* Liste d'articles dans un panier */
.basket-items-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--panel2);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 8px;
  min-height: 120px;
}
.b-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 12px;
}
.b-item-info { flex: 1; min-width: 0; padding-right: 8px; }
.b-item-title { font-weight: 700; color: #fff; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.b-item-sub { font-size: 10.5px; color: var(--mut); }
.b-item-actions { display: flex; align-items: center; gap: 6px; }
.qty-stepper {
  display: flex;
  align-items: center;
  gap: 4px;
  background: var(--panel2);
  border-radius: 6px;
  padding: 2px;
}
.qty-stepper button {
  width: 20px;
  height: 20px;
  background: var(--card);
  border: 1px solid var(--line);
  color: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
}
.qty-stepper span { font-size: 12px; font-weight: 800; min-width: 16px; text-align: center; }

/* Barre de réconciliation fixe */
.reconciliation-bar {
  background: var(--panel);
  border: 1px solid var(--line-strong);
  border-radius: 14px;
  padding: 14px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  box-shadow: 0 4px 20px rgba(0,0,0,0.4);
}
.reconcil-stats { display: flex; align-items: center; gap: 24px; }
.stat-box .l { font-size: 11px; color: var(--mut); font-weight: 700; text-transform: uppercase; }
.stat-box .v { font-family: var(--font-h); font-size: 18px; font-weight: 800; }

.toast-container {
  position: fixed;
  bottom: 20px;
  right: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 1000;
}
.toast {
  background: var(--card);
  border: 1px solid var(--line-strong);
  border-radius: 8px;
  padding: 10px 16px;
  color: #fff;
  font-weight: 600;
  box-shadow: 0 4px 16px rgba(0,0,0,0.5);
  animation: slideIn 0.2s ease;
}
.toast.good { border-color: var(--good); background: #064e3b; }
.toast.warn { border-color: var(--warn); background: #78350f; }
.toast.bad { border-color: var(--bad); background: #7f1d1d; }
@keyframes slideIn { from { transform: translateY(10px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }

/* Navigation d'en-tête (Scission vs Codes-barres) */
.nav-switch {
  display: inline-flex;
  background: var(--panel2);
  border: 1px solid var(--line-strong);
  border-radius: 10px;
  padding: 3px;
  gap: 4px;
}
.nav-btn {
  background: transparent;
  color: var(--mut);
  border: none;
  padding: 6px 14px;
  font-family: inherit;
  font-size: 13px;
  font-weight: 700;
  border-radius: 7px;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all .15s ease;
}
.nav-btn:hover { color: #fff; background: rgba(255,255,255,0.05); }
.nav-btn.active {
  background: var(--pri);
  color: #fff;
  box-shadow: 0 0 12px var(--pri-glow);
}
.nav-badge-warn {
  background: #ef4444;
  color: #fff;
  border-radius: 999px;
  padding: 1px 6px;
  font-size: 11px;
  font-weight: 800;
  line-height: 1.2;
}

/* Badges de statut de code-barres */
.badge-placeholder {
  background: rgba(239, 68, 68, 0.16);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.35);
  border-radius: 6px;
  padding: 2px 7px;
  font-size: 11px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.badge-valid {
  background: rgba(16, 185, 129, 0.15);
  color: var(--good);
  border: 1px solid rgba(16, 185, 129, 0.3);
  border-radius: 6px;
  padding: 2px 7px;
  font-size: 11px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.btn-barcode-quick {
  background: #312e81;
  border-color: #4f46e5;
  color: #e0e7ff;
  padding: 2px 8px;
  font-size: 11px;
}
.btn-barcode-quick:hover {
  background: #3730a3;
  color: #fff;
}

/* Vue Codes-barres Catalogue */
.barcodes-layout {
  display: flex;
  flex-direction: column;
  flex: 1;
  padding: 24px;
  gap: 18px;
  overflow-y: auto;
  max-height: calc(100vh - 57px);
}
.barcodes-header {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.barcodes-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
.b-stat-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.b-stat-card .lbl { font-size: 11.5px; font-weight: 700; color: var(--mut); text-transform: uppercase; }
.b-stat-card .val { font-family: var(--font-h); font-size: 22px; font-weight: 800; color: #fff; }
.b-stat-card.warn { border-color: rgba(245, 158, 11, 0.35); background: rgba(245, 158, 11, 0.08); }
.b-stat-card.warn .val { color: var(--warn); }
.b-stat-card.good { border-color: rgba(16, 185, 129, 0.35); background: rgba(16, 185, 129, 0.08); }
.b-stat-card.good .val { color: var(--good); }

.barcodes-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.search-box { flex: 1; min-width: 260px; max-width: 480px; }
.filter-pills { display: flex; gap: 6px; }
.b-filter-pill {
  background: var(--panel2);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 6px 12px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  color: var(--mut);
  cursor: pointer;
  transition: all .15s ease;
}
.b-filter-pill:hover { color: #fff; border-color: var(--line-strong); }
.b-filter-pill.active { background: var(--pri); border-color: var(--pri); color: #fff; }

.barcodes-table-wrap {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 14px;
  overflow-x: auto;
  overflow-y: auto;
  box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}
.barcodes-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  text-align: left;
}
.barcodes-table th {
  background: var(--panel2);
  color: var(--mut);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 11px 14px;
  border-bottom: 1px solid var(--line-strong);
  position: sticky;
  top: 0;
  z-index: 2;
  white-space: nowrap;
}
.barcodes-table td {
  padding: 10px 14px;
  border-bottom: 1px solid var(--line);
  vertical-align: middle;
}
.barcodes-table tr:hover { background: rgba(255,255,255,0.03); }
.barcodes-table tr.row-placeholder { background: rgba(239, 68, 68, 0.04); }
.barcodes-table tr.row-saved {
  animation: rowFlash 1.4s ease forwards;
}
@keyframes rowFlash {
  0% { background: rgba(16, 185, 129, 0.35); }
  100% { background: transparent; }
}
.barcodes-table .num { text-align: right; }
.bc-input {
  width: 100%;
  max-width: 240px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  font-weight: 600;
  padding: 6px 10px;
}

/* Modale de saisie de code-barres */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  padding: 20px;
}
.modal-card {
  background: var(--panel);
  border: 1px solid var(--line-strong);
  border-radius: 16px;
  width: 100%;
  max-width: 480px;
  box-shadow: 0 10px 40px rgba(0,0,0,0.6);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  animation: modalPop .2s ease;
}
@keyframes modalPop { from { transform: scale(0.95); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.modal-head {
  padding: 14px 18px;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.modal-head h3 { font-family: var(--font-h); font-size: 15px; font-weight: 700; color: #fff; margin: 0; }
.modal-body { padding: 18px; display: flex; flex-direction: column; }
.modal-foot {
  padding: 12px 18px;
  border-top: 1px solid var(--line);
  background: var(--panel2);
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
</head>
<body>

<header class="top">
  <div class="brand">
    <span style="font-size:22px">🛠️</span>
    <div>
      <h1>Atelier de Scission & Codes-barres Catalogue</h1>
      <div style="font-size:11px;color:var(--mut)">eLib · Scission des ventes &amp; Renseignement des codes-barres manquants</div>
    </div>
    <span class="badge-ephemere">Outil Éphémère</span>
  </div>

  <div class="nav-switch">
    <button class="nav-btn active" id="btnNavSplit" onclick="switchMainView('split')">
      ✂️ Scission des Ventes
    </button>
    <button class="nav-btn" id="btnNavBarcode" onclick="switchMainView('barcodes')">
      🏷️ Codes-barres Catalogue <span class="nav-badge-warn" id="navPlaceholderBadge" style="display:none">0</span>
    </button>
  </div>

  <div style="display:flex;align-items:center;gap:10px">
    <button class="btn sm" id="btnManualBackup" title="Créer une sauvegarde immédiate de précaution">
      💾 Sauvegarde de sécurité
    </button>
  </div>
</header>

<!-- Vue 1 : Atelier de Scission des Ventes -->
<div class="layout" id="splitLayout">
  <!-- Colonne Gauche : Liste des Ventes -->
  <aside class="sidebar">
    <div class="sidebar-title">
      <span>Ventes à traiter (<b id="saleCount">14</b>)</span>
      <span id="totalHistoricalCA" style="color:var(--good);font-weight:800">0,00 €</span>
    </div>
    <div style="display:flex;gap:4px;padding:8px 10px;border-bottom:1px solid var(--line);background:rgba(0,0,0,0.25)">
      <button class="b-filter-pill active" id="btnFilterHist" style="flex:1;text-align:center;padding:5px 6px;font-size:11px" onclick="setSalesFilter('historical')">
        📦 14 Historiques (<span id="countPillHist">14</span>)
      </button>
      <button class="b-filter-pill" id="btnFilterAllSales" style="flex:1;text-align:center;padding:5px 6px;font-size:11px" onclick="setSalesFilter('all')">
        Toutes (<span id="countPillAll">35</span>)
      </button>
    </div>
    <div class="sales-list" id="salesListContainer">
      <div style="color:var(--mut);font-size:12px;text-align:center;padding:20px">Chargement des ventes...</div>
    </div>
  </aside>

  <!-- Zone Principale : Atelier -->
  <main class="workspace" id="workspace">
    <div class="empty-state">
      <svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
        <line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/>
      </svg>
      <h3 style="color:#fff;margin-bottom:4px">Sélectionnez une vente à inspecter ou scinder</h3>
      <p style="font-size:12px">Cliquez sur l'une des 14 ventes à gauche pour ouvrir l'atelier de réparation et de qualification.</p>
    </div>
  </main>
</div>

<!-- Vue 2 : Gestion des Codes-barres Catalogue -->
<div class="barcodes-layout" id="barcodesLayout" style="display:none">
  <div class="barcodes-header">
    <div class="barcodes-stats">
      <div class="b-stat-card">
        <span class="lbl">Total Ouvrages au catalogue</span>
        <b class="val" id="bcTotalBooks">0</b>
      </div>
      <div class="b-stat-card warn">
        <span class="lbl">⚠️ Codes provisoires / manquants à renseigner</span>
        <b class="val" id="bcPlaceholderCount">0</b>
      </div>
      <div class="b-stat-card good">
        <span class="lbl">✓ Codes EAN-13 conformes</span>
        <b class="val" id="bcValidCount">0</b>
      </div>
    </div>

    <div class="barcodes-toolbar">
      <div class="search-box">
        <input type="text" id="bcSearchInput" class="text-input" placeholder="🔍 Rechercher un ouvrage par titre, auteur, code actuel..." oninput="filterBooks()">
      </div>
      <div class="filter-pills">
        <button class="b-filter-pill active" id="pillPlaceholder" onclick="setBookFilter('placeholder')">
          ⚠️ Codes provisoires (<span id="pillCountPlaceholder">0</span>)
        </button>
        <button class="b-filter-pill" id="pillAll" onclick="setBookFilter('all')">
          Tous les ouvrages (<span id="pillCountAll">0</span>)
        </button>
        <button class="b-filter-pill" id="pillValid" onclick="setBookFilter('valid')">
          ✓ Codes valides (<span id="pillCountValid">0</span>)
        </button>
      </div>
    </div>
  </div>

  <div class="barcodes-table-wrap">
    <table class="barcodes-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Titre de l'ouvrage</th>
          <th>Auteur / Éditeur</th>
          <th class="num">Prix</th>
          <th class="num">Ventes</th>
          <th class="num">Stock</th>
          <th>Code actuel</th>
          <th style="min-width:240px">Nouveau Code EAN-13</th>
          <th class="num">Action</th>
        </tr>
      </thead>
      <tbody id="barcodesTableBody">
        <tr><td colspan="9" style="text-align:center;padding:30px;color:var(--mut)">Chargement du catalogue...</td></tr>
      </tbody>
    </table>
  </div>
</div>

<!-- Modal Rapide de Saisie de Code-barres -->
<div class="modal-overlay" id="barcodeModal" style="display:none" onclick="if(event.target===this) closeBarcodeModal()">
  <div class="modal-card">
    <div class="modal-head">
      <h3>🏷️ Renseigner le Code-barres</h3>
      <button class="btn sm" onclick="closeBarcodeModal()">✕</button>
    </div>
    <div class="modal-body">
      <div style="font-size:11px;color:var(--mut);text-transform:uppercase;font-weight:700">Ouvrage sélectionné</div>
      <div style="font-weight:700;font-size:14px;color:#fff;margin:2px 0 6px" id="modalBookTitle">Titre</div>
      <div style="font-size:12px;color:var(--mut);margin-bottom:14px">
        Code actuel : <span id="modalCurrentCode" class="badge-placeholder">ICCREN-1</span>
      </div>
      
      <div class="form-group">
        <label>Nouveau Code EAN-13 / ISBN (13 chiffres)</label>
        <input type="text" class="text-input" id="modalNewCodeInput" placeholder="Ex: 9782847000123" style="font-size:14px;padding:8px 12px;letter-spacing:0.5px" onkeydown="if(event.key==='Enter') saveBarcodeFromModal()">
        <small style="color:var(--mut);font-size:11px;margin-top:4px">Une sauvegarde de précaution automatique sera générée avant d'enregistrer.</small>
      </div>
    </div>
    <div class="modal-foot">
      <button class="btn sm" onclick="closeBarcodeModal()">Annuler</button>
      <button class="btn pri" id="btnModalSaveBarcode" onclick="saveBarcodeFromModal()">💾 Enregistrer le code-barres</button>
    </div>
  </div>
</div>

<div class="toast-container" id="toastContainer"></div>

<script>
let currentSales = [];
let activeSaleId = null;
let activeSaleData = null; // { sale, lines, payments }
let activeTab = 'split';   // 'split' | 'edit'
let splitBaskets = [];     // [{ id, is_original, date, payment, customer_gender, customer_age_group, is_star, service_moment, note, items: [{ line_id, qty }] }]

function toast(msg, type='good') {
  const c = document.getElementById('toastContainer');
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => { t.style.opacity = '0'; setTimeout(() => t.remove(), 200); }, 3500);
}

function eur(v) {
  return (Number(v) || 0).toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
}

let salesFilter = 'historical'; // 'historical' | 'all'

async function api(path, method='GET', body=null) {
  try {
    const opt = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opt.body = JSON.stringify(body);
    const res = await fetch(path, opt);
    const data = await res.json();
    return data;
  } catch (err) {
    console.error('API Error:', path, err);
    return { ok: false, error: err.message || 'Erreur réseau' };
  }
}

// -----------------------------------------------------------------------------
// GESTION ET FILTRAGE DES VENTES
// -----------------------------------------------------------------------------
function setSalesFilter(filter) {
  salesFilter = filter;
  const btnH = document.getElementById('btnFilterHist');
  const btnA = document.getElementById('btnFilterAllSales');
  if (btnH) btnH.classList.toggle('active', filter === 'historical');
  if (btnA) btnA.classList.toggle('active', filter === 'all');
  renderSalesList();
}

function renderSalesList() {
  const container = document.getElementById('salesListContainer');
  if (!container) return;

  const filtered = currentSales.filter(s => {
    if (salesFilter === 'historical') {
      return s.id <= 14 || s.is_compressed || s.note === 'Import Excel';
    }
    return true;
  });

  const histList = currentSales.filter(s => s.id <= 14 || s.is_compressed || s.note === 'Import Excel');
  const sc = document.getElementById('saleCount');
  if (sc) sc.textContent = filtered.length;
  const cPh = document.getElementById('countPillHist');
  if (cPh) cPh.textContent = histList.length;
  const cPa = document.getElementById('countPillAll');
  if (cPa) cPa.textContent = currentSales.length;

  const totalCA = filtered.reduce((s, x) => s + x.total_rev, 0);
  const tCa = document.getElementById('totalHistoricalCA');
  if (tCa) tCa.textContent = eur(totalCA);

  container.innerHTML = '';
  if (!filtered.length) {
    container.innerHTML = '<div style="color:var(--mut);font-size:12px;text-align:center;padding:30px">Aucune vente ne correspond à ce filtre.</div>';
    return;
  }

  filtered.forEach(s => {
    const el = document.createElement('div');
    el.className = 'sale-item' + (s.id === activeSaleId ? ' active' : '');
    el.dataset.id = s.id;
    el.onclick = () => selectSale(s.id);

    const isQual = s.customer_gender || s.customer_age_group || s.is_star;
    const tag = s.is_compressed
      ? '<span class="tag-compressed">📦 ' + s.total_qty + ' ex (' + s.line_count + ' réf)</span>'
      : '<span class="tag-qual">✓ 1 article</span>';

    el.innerHTML = `
      <div class="top-line">
        <span class="sale-id">Vente #${s.id}</span>
        <span class="sale-total">${eur(s.total_rev)}</span>
      </div>
      <div class="sale-sub">
        <span>📅 ${s.date}</span>
        <span>💳 ${s.payment}</span>
        ${tag}
      </div>
      ${isQual ? `<div style="font-size:10.5px;color:#c4b5fd;margin-top:3px">👤 ${s.customer_gender || ''} ${s.customer_age_group ? '· ' + s.customer_age_group : ''} ${s.is_star ? '⭐' : ''}</div>` : ''}
    `;
    container.appendChild(el);
  });
}

// -----------------------------------------------------------------------------
// CHARGEMENT INITIAL DES VENTES
// -----------------------------------------------------------------------------
async function loadSales() {
  const data = await api('/api/sales');
  if (!data.ok) return toast('Erreur de chargement des ventes : ' + (data.error || 'Erreur inconnue'), 'bad');
  currentSales = data.sales || [];
  renderSalesList();

  // Auto-sélection de la première vente si aucune n'est active
  if (!activeSaleId && currentSales.length > 0) {
    const firstSale = currentSales.find(s => s.id <= 14) || currentSales[0];
    if (firstSale) {
      selectSale(firstSale.id);
    }
  }
}

// -----------------------------------------------------------------------------
// SÉLECTION D'UNE VENTE & INITIALISATION DE L'ATELIER
// -----------------------------------------------------------------------------
async function selectSale(id) {
  activeSaleId = id;
  // Rafraîchir la surbrillance active sans recharger toute l'API
  document.querySelectorAll('.sale-item').forEach(el => {
    el.classList.toggle('active', el.dataset.id == id);
  });

  const res = await api('/api/sales/' + id);
  if (!res.ok) return toast('Impossible de charger la vente #' + id + ' : ' + (res.error || ''), 'bad');
  activeSaleData = res;

  // Initialiser les paniers de scission par défaut :
  // Panier 1 reçoit tout par défaut au départ
  splitBaskets = [
    {
      id: 1,
      is_original: true,
      date: activeSaleData.sale.date,
      payment: activeSaleData.sale.payment || 'Espèces',
      customer_gender: activeSaleData.sale.customer_gender || '',
      customer_age_group: activeSaleData.sale.customer_age_group || '',
      is_star: activeSaleData.sale.is_star || 0,
      service_moment: activeSaleData.sale.service_moment || '',
      note: activeSaleData.sale.note || '',
      items: activeSaleData.lines.map(l => ({ line_id: l.id, qty: l.qty }))
    }
  ];

  renderWorkspace();
}

// -----------------------------------------------------------------------------
// RENDU DE L'ATELIER CENTRAL
// -----------------------------------------------------------------------------
function renderWorkspace() {
  const ws = document.getElementById('workspace');
  if (!activeSaleData) return;

  const s = activeSaleData.sale;
  const lines = activeSaleData.lines;
  const origTotal = lines.reduce((acc, l) => acc + l.total_price, 0);
  const origQty = lines.reduce((acc, l) => acc + l.qty, 0);

  ws.innerHTML = `
    <div class="sale-banner">
      <div>
        <h2>Vente #${s.id} · ${eur(origTotal)} (${origQty} exemplaires au total)</h2>
        <div style="font-size:12px;color:var(--mut);margin-top:2px">
          Date : <b>${s.date}</b> · Moyen de paiement initial : <b>${s.payment}</b> · Note : <i>${s.note || 'Aucune'}</i>
        </div>
      </div>
      <div>
        <span class="tag-compressed" style="font-size:12px;padding:4px 10px">
          ${lines.length} référence${lines.length > 1 ? 's' : ''}
        </span>
      </div>
    </div>

    <div class="tabs">
      <button class="tab-btn ${activeTab === 'split' ? 'active' : ''}" onclick="setTab('split')">
        ✂️ Scinder en plusieurs paniers (${splitBaskets.length})
      </button>
      <button class="tab-btn ${activeTab === 'edit' ? 'active' : ''}" onclick="setTab('edit')">
        ✏️ Modifier le profil (sans scission)
      </button>
    </div>

    <div id="tabContent"></div>
  `;

  if (activeTab === 'split') {
    renderSplitTab();
  } else {
    renderEditTab();
  }
}

function setTab(t) {
  activeTab = t;
  renderWorkspace();
}

// -----------------------------------------------------------------------------
// TAB 1 : SCISSION EN PLUSIEURS PANIERS
// -----------------------------------------------------------------------------
function renderSplitTab() {
  const container = document.getElementById('tabContent');
  const lines = activeSaleData.lines;
  const origTotal = lines.reduce((acc, l) => acc + l.total_price, 0);
  const origQty = lines.reduce((acc, l) => acc + l.qty, 0);

  // Calcul des quantités réparties par line_id
  const allocatedMap = {};
  lines.forEach(l => allocatedMap[l.id] = 0);
  splitBaskets.forEach(b => {
    b.items.forEach(it => {
      allocatedMap[it.line_id] = (allocatedMap[it.line_id] || 0) + it.qty;
    });
  });

  // Calcul des totaux par panier
  let totalDistributedRev = 0;
  let totalDistributedQty = 0;

  const basketsHtml = splitBaskets.map((b, bIdx) => {
    let bRev = 0;
    let bQty = 0;

    const itemsHtml = b.items.filter(it => it.qty > 0).map(it => {
      const l = lines.find(x => x.id === it.line_id);
      if (!l) return '';
      const lineCost = it.qty * l.unit_price;
      bRev += lineCost;
      bQty += it.qty;

      const isPlaceholder = !l.code || l.code.length < 10 || /^(NA-|ICCREN-|AUTO-|DUMMY-|TEMP-)/i.test(l.code);
      const codeHtml = (isPlaceholder && !l.is_pack)
        ? `<span class="badge-placeholder">⚠️ Provisoire : ${l.code}</span> <button type="button" class="btn sm btn-barcode-quick" data-book-id="${l.book_id}" onclick="handleBarcodeQuickClick(this)">✎ Renseigner EAN-13</button>`
        : `<span class="badge-valid" style="font-size:10px;padding:1px 5px">✓ ${l.code}</span>`;

      return `
        <div class="b-item">
          <div class="b-item-info">
            <div class="b-item-title">${esc(l.title)}</div>
            <div class="b-item-sub" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-top:2px">
              <span>${eur(l.unit_price)} / ex.</span>
              <span>·</span>
              ${codeHtml}
            </div>
          </div>
          <div class="b-item-actions">
            <div class="qty-stepper">
              <button type="button" onclick="changeItemQty(${bIdx}, ${it.line_id}, -1)">−</button>
              <span>${it.qty}</span>
              <button type="button" onclick="changeItemQty(${bIdx}, ${it.line_id}, 1)">+</button>
            </div>
            <span style="font-weight:700;color:var(--good);min-width:55px;text-align:right">${eur(lineCost)}</span>
            ${splitBaskets.length > 1 ? `
              <select class="select-input" style="padding:2px 4px;font-size:10px" onchange="moveItemToBasket(${bIdx}, ${it.line_id}, this.value)">
                <option value="" disabled selected>Déplacer vers...</option>
                ${splitBaskets.map((ob, oIdx) => oIdx !== bIdx ? `<option value="${oIdx}">Panier ${oIdx + 1}</option>` : '').join('')}
              </select>
            ` : ''}
          </div>
        </div>
      `;
    }).join('');

    totalDistributedRev += bRev;
    totalDistributedQty += bQty;

    return `
      <div class="basket-card">
        <div class="basket-head">
          <div style="display:flex;align-items:center;gap:8px">
            <span class="basket-title">Panier ${bIdx + 1} ${b.is_original ? '<span style="font-size:11px;color:var(--mut);font-weight:400">(Vente #' + activeSaleData.sale.id + ')</span>' : ''}</span>
          </div>
          <div style="display:flex;align-items:center;gap:8px">
            <span class="basket-total-pill">${eur(bRev)} (${bQty} ex.)</span>
            ${!b.is_original ? `<button class="btn sm" style="color:var(--bad)" onclick="removeBasket(${bIdx})">Supprimer</button>` : ''}
          </div>
        </div>

        <!-- Formulaire de Qualification du Panier -->
        <div class="form-grid">
          <div class="form-group">
            <label>Moyen de paiement</label>
            <select class="select-input" onchange="splitBaskets[${bIdx}].payment = this.value">
              ${['Espèces', 'CB', 'Wero', 'Virement', 'Don'].map(p => `<option value="${p}" ${b.payment === p ? 'selected' : ''}>${p}</option>`).join('')}
            </select>
          </div>
          <div class="form-group">
            <label>Culte / Moment</label>
            <select class="select-input" onchange="splitBaskets[${bIdx}].service_moment = this.value">
              <option value="" ${!b.service_moment ? 'selected' : ''}>Non renseigné</option>
              ${['1er Culte', '2e Culte', 'Culte Unique', 'Séminaire / Soirée'].map(m => `<option value="${m}" ${b.service_moment === m ? 'selected' : ''}>${m}</option>`).join('')}
            </select>
          </div>
        </div>

        <div class="form-group">
          <label>Profil Acheteur (Genre)</label>
          <div class="chip-row">
            ${['Femme', 'Homme', 'Couple'].map(g => `
              <button type="button" class="p-chip ${b.customer_gender === g ? 'on' : ''}" onclick="setBasketField(${bIdx}, 'customer_gender', '${b.customer_gender === g ? '' : g}')">
                ${g === 'Femme' ? '♀ Femme' : g === 'Homme' ? '♂ Homme' : '👥 Couple'}
              </button>
            `).join('')}
            <button type="button" class="p-chip ${!b.customer_gender ? 'on' : ''}" style="color:var(--mut)" onclick="setBasketField(${bIdx}, 'customer_gender', '')">Inconnu</button>
          </div>
        </div>

        <div class="form-group">
          <label>Tranche d'âge & Engagement</label>
          <div class="chip-row">
            ${['Enfant / Ado', 'Jeune adulte', 'Adulte', 'Senior'].map(a => `
              <button type="button" class="p-chip ${b.customer_age_group === a ? 'on' : ''}" onclick="setBasketField(${bIdx}, 'customer_age_group', '${b.customer_age_group === a ? '' : a}')">
                ${a === 'Enfant / Ado' ? '<18' : a === 'Jeune adulte' ? '18-29' : a === 'Adulte' ? '30-59' : '60+'}
              </button>
            `).join('')}
            <button type="button" class="p-chip ${b.is_star ? 'star-on' : ''}" onclick="setBasketField(${bIdx}, 'is_star', ${b.is_star ? 0 : 1})">⭐ STAR</button>
          </div>
        </div>

        <!-- Articles du panier -->
        <div style="font-size:11px;font-weight:700;color:var(--mut);text-transform:uppercase;margin-top:4px">Articles attribués</div>
        <div class="basket-items-list">
          ${itemsHtml || '<div style="color:var(--mut);font-size:12px;text-align:center;padding:30px">Aucun article dans ce panier</div>'}
        </div>
      </div>
    `;
  }).join('');

  // Articles restants non alloués ou disponibles
  const unassignedLines = lines.map(l => {
    const left = l.qty - (allocatedMap[l.id] || 0);
    return { ...l, left };
  }).filter(l => l.left > 0);

  const isBalanced = (Math.abs(totalDistributedRev - origTotal) < 0.01) && (totalDistributedQty === origQty);

  container.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
      <div style="font-size:13px;color:var(--mut)">
        Répartissez les livres entre vos différents paniers clients. Vous pouvez en créer autant que nécessaire.
      </div>
      <button class="btn pri sm" onclick="addNewBasket()">
        ＋ Ajouter un nouveau panier
      </button>
    </div>

    ${unassignedLines.length > 0 ? `
      <div style="background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.3);border-radius:10px;padding:10px 14px;margin-bottom:14px">
        <div style="font-weight:700;color:#f87171;font-size:12px;margin-bottom:4px">⚠️ Exemplaires restants à répartir :</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          ${unassignedLines.map(u => `
            <span style="background:var(--card);border:1px solid var(--line);border-radius:6px;padding:3px 8px;font-size:11px">
              <b>${u.left}x</b> ${u.title}
            </span>
          `).join('')}
        </div>
      </div>
    ` : ''}

    <div class="baskets-container" style="margin-bottom:20px">
      ${basketsHtml}
    </div>

    <!-- Barre de réconciliation fixe -->
    <div class="reconciliation-bar">
      <div class="reconcil-stats">
        <div class="stat-box">
          <div class="l">Vente d'origine</div>
          <div class="v" style="color:#fff">${eur(origTotal)} <span style="font-size:13px;color:var(--mut);font-weight:400">(${origQty} ex.)</span></div>
        </div>
        <div class="stat-box">
          <div class="l">Somme des paniers</div>
          <div class="v" style="color:${isBalanced ? 'var(--good)' : 'var(--warn)'}">${eur(totalDistributedRev)} <span style="font-size:13px;color:var(--mut);font-weight:400">(${totalDistributedQty} ex.)</span></div>
        </div>
        <div class="stat-box">
          <div class="l">Statut d'équilibre</div>
          <div class="v" style="font-size:14px;color:${isBalanced ? 'var(--good)' : 'var(--bad)'}">
            ${isBalanced ? '✓ Équilibre parfait (Écart 0,00 €)' : '⚠️ Reliquat : ' + (origQty - totalDistributedQty) + ' ex. restant(s)'}
          </div>
        </div>
      </div>

      <button class="btn good" style="padding:10px 20px;font-size:14px" ${!isBalanced || splitBaskets.length < 2 ? 'disabled' : ''} onclick="confirmAndExecuteSplit()">
        ⚡ Appliquer la scission en base de données
      </button>
    </div>
  `;
}

function setBasketField(bIdx, field, val) {
  splitBaskets[bIdx][field] = val;
  renderSplitTab();
}

function addNewBasket() {
  const orig = activeSaleData.sale;
  splitBaskets.push({
    id: splitBaskets.length + 1,
    is_original: false,
    date: orig.date,
    payment: 'Espèces',
    customer_gender: '',
    customer_age_group: '',
    is_star: 0,
    service_moment: orig.service_moment || '',
    note: `Scission vente #${orig.id} (Panier ${splitBaskets.length + 1})`,
    items: []
  });
  renderSplitTab();
  toast('Nouveau panier ajouté');
}

function removeBasket(bIdx) {
  if (splitBaskets.length <= 1) return;
  const removed = splitBaskets.splice(bIdx, 1)[0];
  // Rebasculer les items du panier supprimé dans le Panier 1
  removed.items.forEach(it => {
    const target = splitBaskets[0].items.find(x => x.line_id === it.line_id);
    if (target) {
      target.qty += it.qty;
    } else {
      splitBaskets[0].items.push({ ...it });
    }
  });
  renderSplitTab();
  toast('Panier supprimé, ses articles ont été reversés dans le Panier 1');
}

function changeItemQty(bIdx, lineId, delta) {
  const basket = splitBaskets[bIdx];
  const item = basket.items.find(x => x.line_id === lineId);
  if (!item) return;

  const line = activeSaleData.lines.find(x => x.id === lineId);
  const totalAllocated = splitBaskets.reduce((sum, b) => {
    const it = b.items.find(x => x.line_id === lineId);
    return sum + (it ? it.qty : 0);
  }, 0);

  if (delta > 0 && totalAllocated + 1 > line.qty) {
    return toast('Tous les exemplaires de ce livre sont déjà répartis', 'warn');
  }
  if (item.qty + delta < 0) return;

  item.qty += delta;
  renderSplitTab();
}

function moveItemToBasket(fromBIdx, lineId, toBIdxStr) {
  const toBIdx = parseInt(toBIdxStr, 10);
  if (isNaN(toBIdx) || toBIdx === fromBIdx) return;

  const fromB = splitBaskets[fromBIdx];
  const toB = splitBaskets[toBIdx];
  const itIdx = fromB.items.findIndex(x => x.line_id === lineId);
  if (itIdx === -1) return;

  const itemToMove = fromB.items.splice(itIdx, 1)[0];
  const existingInTo = toB.items.find(x => x.line_id === lineId);
  if (existingInTo) {
    existingInTo.qty += itemToMove.qty;
  } else {
    toB.items.push(itemToMove);
  }

  renderSplitTab();
  toast(`Article déplacé vers le Panier ${toBIdx + 1}`);
}

async function confirmAndExecuteSplit() {
  if (!confirm(`Confirmer la scission de la vente #${activeSaleData.sale.id} en ${splitBaskets.length} ventes distinctes ?\\n\\nUne sauvegarde complète de précaution sera créée automatiquement.`)) {
    return;
  }

  const payload = {
    baskets: splitBaskets.map(b => ({
      is_original: b.is_original,
      date: b.date,
      payment: b.payment,
      customer_gender: b.customer_gender,
      customer_age_group: b.customer_age_group,
      is_star: b.is_star,
      service_moment: b.service_moment,
      note: b.note,
      items: b.items.filter(it => it.qty > 0)
    }))
  };

  const res = await api(`/api/sales/${activeSaleData.sale.id}/split`, 'POST', payload);
  if (!res.ok) {
    return alert('Erreur lors de la scission : ' + (res.error || 'Erreur inconnue'));
  }

  toast(res.message, 'good');
  await loadSales();
  selectSale(activeSaleData.sale.id);
}

// -----------------------------------------------------------------------------
// TAB 2 : MODIFICATION DU PROFIL SANS SCISSION
// -----------------------------------------------------------------------------
function renderEditTab() {
  const container = document.getElementById('tabContent');
  const s = activeSaleData.sale;

  container.innerHTML = `
    <div style="max-width:540px;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:20px;display:flex;flex-direction:column;gap:14px">
      <h3 style="font-family:var(--font-h);color:#fff">Qualification du profil · Vente #${s.id}</h3>
      <p style="font-size:12px;color:var(--mut)">Cette vente était réellement un panier individuel. Vous pouvez qualifier directement son profil sans la scinder :</p>

      <div class="form-grid">
        <div class="form-group">
          <label>Date de la vente</label>
          <input type="date" class="text-input" id="editDate" value="${s.date}">
        </div>
        <div class="form-group">
          <label>Moyen de paiement</label>
          <select class="select-input" id="editPay">
            ${['Espèces', 'CB', 'Wero', 'Virement', 'Don'].map(p => `<option value="${p}" ${s.payment === p ? 'selected' : ''}>${p}</option>`).join('')}
          </select>
        </div>
      </div>

      <div class="form-group">
        <label>Profil Acheteur (Genre)</label>
        <select class="select-input" id="editGender">
          <option value="" ${!s.customer_gender ? 'selected' : ''}>Non renseigné</option>
          <option value="Femme" ${s.customer_gender === 'Femme' ? 'selected' : ''}>Femme ♀</option>
          <option value="Homme" ${s.customer_gender === 'Homme' ? 'selected' : ''}>Homme ♂</option>
          <option value="Couple" ${s.customer_gender === 'Couple' ? 'selected' : ''}>Couple 👥</option>
        </select>
      </div>

      <div class="form-grid">
        <div class="form-group">
          <label>Tranche d'âge</label>
          <select class="select-input" id="editAge">
            <option value="" ${!s.customer_age_group ? 'selected' : ''}>Non renseigné</option>
            <option value="Enfant / Ado" ${s.customer_age_group === 'Enfant / Ado' ? 'selected' : ''}>Ados (&lt;18)</option>
            <option value="Jeune adulte" ${s.customer_age_group === 'Jeune adulte' ? 'selected' : ''}>Jeunes (18-29)</option>
            <option value="Adulte" ${s.customer_age_group === 'Adulte' ? 'selected' : ''}>Adultes (30-59)</option>
            <option value="Senior" ${s.customer_age_group === 'Senior' ? 'selected' : ''}>Seniors (60+)</option>
          </select>
        </div>
        <div class="form-group">
          <label>Culte / Moment</label>
          <select class="select-input" id="editMoment">
            <option value="" ${!s.service_moment ? 'selected' : ''}>Non renseigné</option>
            ${['1er Culte', '2e Culte', 'Culte Unique', 'Séminaire / Soirée'].map(m => `<option value="${m}" ${s.service_moment === m ? 'selected' : ''}>${m}</option>`).join('')}
          </select>
        </div>
      </div>

      <div class="form-group">
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer">
          <input type="checkbox" id="editStar" ${s.is_star ? 'checked' : ''}>
          <span>Client / Foyer serviteur STAR ⭐</span>
        </label>
      </div>

      <div class="form-group">
        <label>Note / Remarque</label>
        <input type="text" class="text-input" id="editNote" value="${s.note || ''}" placeholder="Remarque optionnelle...">
      </div>

      <button class="btn pri" style="margin-top:8px" onclick="saveEditDirect()">
        💾 Enregistrer les modifications
      </button>
    </div>
  `;
}

async function saveEditDirect() {
  const payload = {
    date: document.getElementById('editDate').value,
    payment: document.getElementById('editPay').value,
    customer_gender: document.getElementById('editGender').value,
    customer_age_group: document.getElementById('editAge').value,
    service_moment: document.getElementById('editMoment').value,
    is_star: document.getElementById('editStar').checked ? 1 : 0,
    note: document.getElementById('editNote').value
  };

  const res = await api(`/api/sales/${activeSaleData.sale.id}/update`, 'POST', payload);
  if (!res.ok) return alert('Erreur : ' + (res.error || 'Erreur inconnue'));

  toast(res.message, 'good');
  await loadSales();
  selectSale(activeSaleData.sale.id);
}

// -----------------------------------------------------------------------------
// GESTION DES CODES-BARRES DU CATALOGUE
// -----------------------------------------------------------------------------
let allBooks = [];
let currentMainView = 'split'; // 'split' | 'barcodes'
let bookFilter = 'placeholder'; // 'placeholder' | 'all' | 'valid'
let bookSearchQuery = '';
let modalActiveBookId = null;

function esc(s) {
  if (s == null) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function loadBooks() {
  const res = await api('/api/books');
  if (!res.ok) {
    toast('Catalogue : ' + (res.error || 'Erreur de chargement'), 'bad');
    return;
  }
  allBooks = res.books || [];
  updateBookCounts();
  if (currentMainView === 'barcodes') {
    renderBarcodesView();
  }
}

function updateBookCounts() {
  const placeholders = allBooks.filter(b => b.is_placeholder);
  const badge = document.getElementById('navPlaceholderBadge');
  if (badge) {
    badge.textContent = placeholders.length;
    badge.style.display = placeholders.length ? 'inline-block' : 'none';
  }
  const bcTotal = document.getElementById('bcTotalBooks');
  if (bcTotal) bcTotal.textContent = allBooks.length;
  const bcPl = document.getElementById('bcPlaceholderCount');
  if (bcPl) bcPl.textContent = placeholders.length;
  const bcVal = document.getElementById('bcValidCount');
  if (bcVal) bcVal.textContent = allBooks.length - placeholders.length;

  const pPl = document.getElementById('pillCountPlaceholder');
  if (pPl) pPl.textContent = placeholders.length;
  const pAll = document.getElementById('pillCountAll');
  if (pAll) pAll.textContent = allBooks.length;
  const pVal = document.getElementById('pillCountValid');
  if (pVal) pVal.textContent = allBooks.length - placeholders.length;
}

function switchMainView(view) {
  currentMainView = view;
  document.getElementById('btnNavSplit').classList.toggle('active', view === 'split');
  document.getElementById('btnNavBarcode').classList.toggle('active', view === 'barcodes');
  
  document.getElementById('splitLayout').style.display = view === 'split' ? 'grid' : 'none';
  document.getElementById('barcodesLayout').style.display = view === 'barcodes' ? 'flex' : 'none';

  if (view === 'barcodes') {
    renderBarcodesView();
  }
}

function setBookFilter(filter) {
  bookFilter = filter;
  ['placeholder', 'all', 'valid'].forEach(f => {
    const el = document.getElementById('pill' + f.charAt(0).toUpperCase() + f.slice(1));
    if (el) el.classList.toggle('active', f === filter);
  });
  renderBarcodesView();
}

function filterBooks() {
  bookSearchQuery = (document.getElementById('bcSearchInput').value || '').trim().toLowerCase();
  renderBarcodesView();
}

function renderBarcodesView() {
  updateBookCounts();
  const tb = document.getElementById('barcodesTableBody');
  if (!tb) return;

  let filtered = allBooks.filter(b => {
    if (bookFilter === 'placeholder' && !b.is_placeholder) return false;
    if (bookFilter === 'valid' && b.is_placeholder) return false;
    if (bookSearchQuery) {
      const matchTitle = (b.title || '').toLowerCase().includes(bookSearchQuery);
      const matchAuthor = (b.author || '').toLowerCase().includes(bookSearchQuery);
      const matchCode = (b.code || '').toLowerCase().includes(bookSearchQuery);
      if (!matchTitle && !matchAuthor && !matchCode) return false;
    }
    return true;
  });

  if (!filtered.length) {
    tb.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:40px;color:var(--mut)">Aucun ouvrage ne correspond à ce filtre.</td></tr>`;
    return;
  }

  tb.innerHTML = filtered.map(b => `
    <tr id="bookRow_${b.id}" class="${b.is_placeholder ? 'row-placeholder' : ''}">
      <td class="muted" style="font-size:11px">#${b.id}</td>
      <td style="font-weight:700;color:#fff">${esc(b.title)}</td>
      <td class="muted" style="font-size:12px">${esc(b.author || '—')} ${b.publisher ? `<small>(${esc(b.publisher)})</small>` : ''}</td>
      <td class="num font-h" style="font-weight:700;color:var(--text)">${eur(b.price)}</td>
      <td class="num muted">${b.sales_count}</td>
      <td class="num muted">${b.stock_est}</td>
      <td>
        ${b.is_placeholder ? `<span class="badge-placeholder">⚠️ ${esc(b.code || 'VIDE')}</span>` : `<span class="badge-valid">✓ ${esc(b.code)}</span>`}
      </td>
      <td>
        <input type="text" class="text-input bc-input" id="input_bc_${b.id}" data-id="${b.id}" placeholder="${b.is_placeholder ? 'Saisir EAN-13 (13 chiffres)...' : 'Modifier le code...'}" value="${b.is_placeholder ? '' : esc(b.code)}" onkeydown="if(event.key==='Enter') saveBookBarcode(${b.id})">
      </td>
      <td class="num">
        <button class="btn pri sm" id="btn_save_${b.id}" onclick="saveBookBarcode(${b.id})">💾 Enregistrer</button>
      </td>
    </tr>
  `).join('');
}

async function saveBookBarcode(bookId) {
  const inp = document.getElementById(`input_bc_${bookId}`);
  if (!inp) return;
  const newCode = inp.value.trim();
  if (!newCode) {
    return toast('Veuillez saisir un code-barres non vide', 'warn');
  }

  const btn = document.getElementById(`btn_save_${bookId}`);
  if (btn) btn.disabled = true;

  const res = await api(`/api/books/${bookId}/barcode`, 'POST', { code: newCode });
  if (btn) btn.disabled = false;

  if (!res.ok) {
    return alert('Erreur : ' + (res.error || "Impossible d'enregistrer"));
  }

  toast(res.message, 'good');

  // Mettre à jour allBooks
  const book = allBooks.find(b => b.id === bookId);
  if (book) {
    book.code = newCode;
    book.is_placeholder = false;
  }

  // Mettre à jour la vente active si elle contient ce livre
  if (activeSaleData && activeSaleData.lines) {
    activeSaleData.lines.forEach(l => {
      if (l.book_id === bookId) l.code = newCode;
    });
    if (activeTab === 'split') renderSplitTab();
  }

  // Animation visuelle de succès
  const row = document.getElementById(`bookRow_${bookId}`);
  if (row) {
    row.classList.remove('row-placeholder');
    row.classList.add('row-saved');
  }

  updateBookCounts();

  // Focus automatique sur le prochain champ placeholder si présent
  const nextPlaceholderInput = document.querySelector('.row-placeholder .bc-input');
  if (nextPlaceholderInput) {
    nextPlaceholderInput.focus();
  }
}

// Modal rapide pour la scission
function handleBarcodeQuickClick(btn) {
  const bookId = Number(btn.dataset.bookId);
  const book = allBooks.find(b => b.id === bookId) || (activeSaleData && activeSaleData.lines ? activeSaleData.lines.find(x => x.book_id === bookId) : null);
  if (!book) return;
  openBarcodeModal(bookId, book.title, book.code);
}

function openBarcodeModal(bookId, title, currentCode) {
  modalActiveBookId = bookId;
  document.getElementById('modalBookTitle').textContent = title;
  document.getElementById('modalCurrentCode').textContent = currentCode || 'VIDE';
  const inp = document.getElementById('modalNewCodeInput');
  inp.value = '';
  document.getElementById('barcodeModal').style.display = 'flex';
  setTimeout(() => inp.focus(), 50);
}

function closeBarcodeModal() {
  document.getElementById('barcodeModal').style.display = 'none';
  modalActiveBookId = null;
}

async function saveBarcodeFromModal() {
  if (!modalActiveBookId) return;
  const inp = document.getElementById('modalNewCodeInput');
  const newCode = inp.value.trim();
  if (!newCode) return toast('Veuillez saisir un code-barres non vide', 'warn');

  const btn = document.getElementById('btnModalSaveBarcode');
  btn.disabled = true;
  const res = await api(`/api/books/${modalActiveBookId}/barcode`, 'POST', { code: newCode });
  btn.disabled = false;

  if (!res.ok) {
    return alert('Erreur : ' + (res.error || "Impossible d'enregistrer"));
  }

  toast(res.message, 'good');

  // Mettre à jour allBooks
  const book = allBooks.find(b => b.id === modalActiveBookId);
  if (book) {
    book.code = newCode;
    book.is_placeholder = false;
  }

  // Mettre à jour la vente active
  if (activeSaleData && activeSaleData.lines) {
    activeSaleData.lines.forEach(l => {
      if (l.book_id === modalActiveBookId) l.code = newCode;
    });
    if (activeTab === 'split') renderSplitTab();
  }

  closeBarcodeModal();
  updateBookCounts();
}

// Raccourci clavier Échap pour fermer la modale
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeBarcodeModal();
});

// -----------------------------------------------------------------------------
// SAUVEGARDE MANUELLE
// -----------------------------------------------------------------------------
document.getElementById('btnManualBackup').onclick = async () => {
  const res = await api('/api/backup', 'POST');
  if (res.ok) {
    toast('Sauvegarde créée dans data/sauvegardes/', 'good');
  } else {
    toast('Erreur de sauvegarde', 'bad');
  }
};

// Initialisation globale
Promise.all([loadSales(), loadBooks()]).catch(e => console.error('Init error:', e));
</script>
</body>
</html>
"""

def free_port_if_stuck(port=PORT):
    """Tue automatiquement tout ancien processus orphelin bloqué sur le port."""
    if sys.platform == "win32":
        try:
            import subprocess
            out = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True).decode(errors="ignore")
            my_pid = os.getpid()
            for line in out.strip().splitlines():
                if "LISTENING" in line:
                    parts = line.strip().split()
                    pid = int(parts[-1])
                    if pid != my_pid:
                        print(f"    [Nettoyage] Libération du port {port} (arrêt processus fantôme PID {pid})...")
                        os.system(f"taskkill /F /PID {pid} >nul 2>&1")
        except Exception:
            pass


def run_server():
    free_port_if_stuck(PORT)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), SalesRepairHandler)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{PORT}"
    print("=" * 76)
    print("[ATELIER] LIBRAIRI-E : ATELIER EPHEMERE DE SCISSION DES VENTES")
    print("    Outil autonome (aucune dependance requise, aucun impact sur l'app de prod)")
    print("-" * 76)
    print(f"    Base connectée      : {DB_PATH}")
    print(f"    Serveur démarré sur : {url}")
    print("    Ouverture automatique dans votre navigateur...")
    print("    Appuyez sur Ctrl+C dans ce terminal lorsque vous avez terminé.")
    print("=" * 76)

    # Ouvrir le navigateur après un court délai
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt de l'outil. À bientôt !")
        server.server_close()


if __name__ == "__main__":
    run_server()
