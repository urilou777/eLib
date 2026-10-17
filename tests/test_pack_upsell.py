import unittest
import sqlite3
import shutil
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app import db, main

class TestPackUpsell(unittest.TestCase):
    def setUp(self):
        self.test_db = "data/test_upsell.db"
        shutil.copy("data/librairie.db", self.test_db)
        self.con = sqlite3.connect(self.test_db)
        self.con.row_factory = sqlite3.Row
        self.c = self.con.cursor()

    def tearDown(self):
        self.con.close()
        if os.path.exists(self.test_db):
            os.remove(self.test_db)

    def test_suggested_packs_for_ruth(self):
        b = self.c.execute("SELECT * FROM books WHERE id = 36").fetchone() # Ruth
        res = main._mobile_book(self.c, b)
        self.assertEqual(res["id"], 36)
        self.assertGreater(len(res["suggested_packs"]), 0)
        pack = res["suggested_packs"][0]
        self.assertEqual(pack["id"], 60) # PACK Ruth & Marie
        self.assertEqual(pack["price"], 35.0)
        self.assertEqual(pack["saving"], 5.0)
        self.assertIn("MARIE", pack["other_items"])
        self.assertGreater(pack["stock"], 0)

    def test_pack_sale_creation_with_components(self):
        # Pack 60
        pack = self.c.execute("SELECT * FROM books WHERE id = 60").fetchone()
        items = self.c.execute("""
            SELECT pi.book_id, pi.qty, bk.title, bk.price
            FROM pack_items pi JOIN books bk ON bk.id = pi.book_id
            WHERE pi.pack_id = 60
        """).fetchall()

        allocs = []
        for it in items:
            lots = db.rows(self.c, f"""
                SELECT l.id, ({db.LOT_REMAINING}) remaining
                FROM lots l JOIN owners o ON o.id = l.owner_id
                WHERE l.book_id = ? AND ({db.LOT_REMAINING}) > 0
                ORDER BY o.priority, l.date, l.id
            """, (it["book_id"],))
            self.assertTrue(len(lots) > 0, f"Stock missing for component {it['title']}")
            allocs.append({"book_id": it["book_id"], "lot_id": lots[0]["id"], "qty": it["qty"]})

        sid, warns = db.create_sale(self.c, "2026-10-17", "CB", "Test vente pack", [{
            "book_id": 60,
            "qty": 1,
            "unit_price": 35.0,
            "allocations": allocs
        }], manual=True, user_name="TestUpsell")
        self.con.commit()

        self.assertIsNotNone(sid)
        sale = self.c.execute("SELECT * FROM sales WHERE id = ?", (sid,)).fetchone()
        self.assertIsNotNone(sale)

        # Vérifier que les allocations ont bien été insérées pour chaque composant
        alloc_rows = self.c.execute("""
            SELECT a.book_id, a.qty, a.revenue, a.due
            FROM allocations a
            JOIN sale_lines sl ON sl.id = a.line_id
            WHERE sl.sale_id = ?
        """, (sid,)).fetchall()

        self.assertEqual(len(alloc_rows), 2)
        total_rev = sum(a["revenue"] for a in alloc_rows)
        self.assertAlmostEqual(total_rev, 35.0, places=2)

if __name__ == "__main__":
    unittest.main()
