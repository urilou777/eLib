"""Test unitaire de la logique de scission atomique de ventes."""
import sqlite3
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import db
from tools.repair_sales_gui import execute_split

def test_split_logic():
    test_db = "data/test_split_temp.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    # Création du schéma complet
    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)

    with conn:
        # Données de test
        conn.execute("INSERT INTO owners(id, name, kind, reverse_pct) VALUES(1, 'Cité Royale', 'maison_mere', 100)")
        conn.execute("INSERT INTO books(id, code, title, price) VALUES(1, 'BK-1', 'Livre Un', 20.0)")
        conn.execute("INSERT INTO books(id, code, title, price) VALUES(2, 'BK-2', 'Livre Deux', 15.0)")
        conn.execute("INSERT INTO lots(id, book_id, owner_id, date, qty_in) VALUES(1, 1, 1, '2026-07-26', 10)")
        conn.execute("INSERT INTO lots(id, book_id, owner_id, date, qty_in) VALUES(2, 2, 1, '2026-07-26', 10)")

        # Création d'une vente compressée (3 ex de BK-1 à 20€ + 2 ex de BK-2 à 15€ = 90€)
        sale_id = conn.execute("""
            INSERT INTO sales(date, payment, note, user_name)
            VALUES('2026-07-26', 'Espèces', 'Import Excel', 'Anonyme')
        """).lastrowid

        l1 = conn.execute("INSERT INTO sale_lines(sale_id, book_id, qty, unit_price) VALUES(?, 1, 3, 20.0)", (sale_id,)).lastrowid
        l2 = conn.execute("INSERT INTO sale_lines(sale_id, book_id, qty, unit_price) VALUES(?, 2, 2, 15.0)", (sale_id,)).lastrowid

        conn.execute("INSERT INTO allocations(line_id, book_id, lot_id, owner_id, qty, revenue, due, date) VALUES(?, 1, 1, 1, 3, 60.0, 60.0, '2026-07-26')", (l1,))
        conn.execute("INSERT INTO allocations(line_id, book_id, lot_id, owner_id, qty, revenue, due, date) VALUES(?, 2, 2, 1, 2, 30.0, 30.0, '2026-07-26')", (l2,))
        conn.execute("INSERT INTO sale_payments(sale_id, payment, amount) VALUES(?, 'Espèces', 90.0)", (sale_id,))
    conn.close()

    # Rediriger temporairement tools.repair_sales_gui.DB_PATH vers test_db
    import tools.repair_sales_gui as tool
    tool.DB_PATH = test_db

    # Exécuter la scission en 2 paniers :
    # Panier 1 (Origine) : 1 ex de BK-1 (20€) + 1 ex de BK-2 (15€) = 35€ (Femme, 30-59, Star=1, CB)
    # Panier 2 (Nouveau) : 2 ex de BK-1 (40€) + 1 ex de BK-2 (15€) = 55€ (Homme, 18-29, Star=0, Espèces)
    baskets = [
        {
            "is_original": True,
            "date": "2026-07-26",
            "payment": "CB",
            "customer_gender": "Femme",
            "customer_age_group": "30-59",
            "is_star": 1,
            "service_moment": "1er Culte",
            "note": "Panier 1 scindé",
            "items": [
                {"line_id": l1, "qty": 1},
                {"line_id": l2, "qty": 1}
            ]
        },
        {
            "is_original": False,
            "date": "2026-07-26",
            "payment": "Espèces",
            "customer_gender": "Homme",
            "customer_age_group": "18-29",
            "is_star": 0,
            "service_moment": "1er Culte",
            "note": "Panier 2 scindé",
            "items": [
                {"line_id": l1, "qty": 2},
                {"line_id": l2, "qty": 1}
            ]
        }
    ]

    res = tool.execute_split(sale_id, baskets)
    assert res["ok"] is True
    assert len(res["created_sales"]) == 1
    new_sale_id = res["created_sales"][0]

    # Vérifications en base
    c = sqlite3.connect(test_db)
    c.row_factory = sqlite3.Row

    # 1. Vérifier la vente 1
    s1 = c.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
    assert s1["payment"] == "CB"
    assert s1["customer_gender"] == "Femme"
    assert s1["customer_age_group"] == "30-59"
    assert s1["is_star"] == 1

    # 2. Vérifier la nouvelle vente
    s2 = c.execute("SELECT * FROM sales WHERE id = ?", (new_sale_id,)).fetchone()
    assert s2["payment"] == "Espèces"
    assert s2["customer_gender"] == "Homme"
    assert s2["customer_age_group"] == "18-29"
    assert s2["is_star"] == 0

    # 3. Vérifier les lignes et montants de la vente 1
    lines1 = c.execute("SELECT * FROM sale_lines WHERE sale_id = ?", (sale_id,)).fetchall()
    tot1 = sum(l["qty"] * l["unit_price"] for l in lines1)
    assert tot1 == 35.0, f"Total panier 1 attendu 35.0, obtenu {tot1}"

    # 4. Vérifier les lignes et montants de la vente 2
    lines2 = c.execute("SELECT * FROM sale_lines WHERE sale_id = ?", (new_sale_id,)).fetchall()
    tot2 = sum(l["qty"] * l["unit_price"] for l in lines2)
    assert tot2 == 55.0, f"Total panier 2 attendu 55.0, obtenu {tot2}"

    # 5. Vérifier la somme globale = 90.0 €
    assert tot1 + tot2 == 90.0

    # 6. Vérifier la somme des allocations globales (quantités, CA, reversions)
    tot_alloc_qty = c.execute("SELECT SUM(qty) FROM allocations").fetchone()[0]
    tot_alloc_rev = c.execute("SELECT SUM(revenue) FROM allocations").fetchone()[0]
    tot_alloc_due = c.execute("SELECT SUM(due) FROM allocations").fetchone()[0]

    assert tot_alloc_qty == 5, f"Quantité allouée attendue 5, obtenue {tot_alloc_qty}"
    assert tot_alloc_rev == 90.0, f"CA alloué attendu 90.0, obtenu {tot_alloc_rev}"
    assert tot_alloc_due == 90.0, f"Dû attendu 90.0, obtenu {tot_alloc_due}"

    # 7. Vérifier sale_payments
    p1 = c.execute("SELECT amount FROM sale_payments WHERE sale_id = ?", (sale_id,)).fetchone()[0]
    p2 = c.execute("SELECT amount FROM sale_payments WHERE sale_id = ?", (new_sale_id,)).fetchone()[0]
    assert p1 == 35.0
    assert p2 == 55.0

    c.close()
    if os.path.exists(test_db):
        os.remove(test_db)
    print("[OK] TEST LOGIQUE SCISSION : 100% SUCCES (Tous les invariants verifies)")

if __name__ == "__main__":
    test_split_logic()
