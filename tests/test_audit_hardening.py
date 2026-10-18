"""Tests unitaires pour les patchs de durcissement (Anti-régression, RGPD, Injection Excel, Concurrence)."""
import unittest
import sqlite3
import os
import sys
from datetime import date, timedelta
from starlette.datastructures import Headers

from app import db, excel_io
from app.main import _dump, BookIn, ResIn, gdpr_info, gdpr_cleanup


class FakeRequest:
    def __init__(self, host="127.0.0.1", user="Admin"):
        self.headers = Headers({"X-User": user})
        self.client = type("Client", (), {"host": host})()
        self.query_params = {}
        self.state = type("State", (), {"role": "desk", "device": None})()


class TestAuditHardening(unittest.TestCase):
    def setUp(self):
        self.test_db = os.path.join(db.DATA_DIR, "test_hardening.db")
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        self.orig_db = db.DB_PATH
        db.DB_PATH = self.test_db
        db.init()

    def tearDown(self):
        db.DB_PATH = self.orig_db
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except OSError:
                pass

    def test_pydantic_dump_compatibility(self):
        """Vérifie que _dump sérialise fidèlement sans dépréciation."""
        bk = BookIn(code="ISBN-9781234567890", title="Ouvrage de Test", price=19.99)
        dumped = _dump(bk)
        self.assertEqual(dumped["code"], "ISBN-9781234567890")
        self.assertEqual(dumped["title"], "Ouvrage de Test")
        self.assertEqual(dumped["price"], 19.99)

    def test_excel_formula_sanitization(self):
        """Vérifie la neutralisation des injections de formules Excel / CSV (OWASP / ANSSI)."""
        self.assertEqual(excel_io._sanitize_cell("=1+1"), "'=1+1")
        self.assertEqual(excel_io._sanitize_cell("+cmd|' /C calc'!A0"), "'+cmd|' /C calc'!A0")
        self.assertEqual(excel_io._sanitize_cell("-20.5"), "'-20.5")
        self.assertEqual(excel_io._sanitize_cell("@SUM(A1:A10)"), "'@SUM(A1:A10)")
        self.assertEqual(excel_io._sanitize_cell("Texte normal"), "Texte normal")
        self.assertEqual(excel_io._sanitize_cell(42), 42)
        self.assertEqual(excel_io._sanitize_cell(19.99), 19.99)

    def test_tx_immediate_locking(self):
        """Vérifie l'exécution d'une transaction avec verrouillage immédiat (BEGIN IMMEDIATE)."""
        with db.tx(immediate=True) as c:
            c.execute("INSERT INTO dropdown_options(group_key, label) VALUES('test_grp', 'Test Opt')")
            row = c.execute("SELECT label FROM dropdown_options WHERE group_key='test_grp'").fetchone()
            self.assertEqual(row["label"], "Test Opt")

    def test_gdpr_reservation_cleanup(self):
        """Vérifie l'anonymisation conforme RGPD des réservations terminées."""
        old_date = (date.today() - timedelta(days=120)).isoformat()
        with db.tx() as c:
            c.execute("INSERT INTO reservations(name, phone, title, qty, date, status, note) VALUES(?,?,?,?,?,?,?)",
                      ("Jean Dupont", "0601020304", "Bible d'étude", 1, old_date, "Servie", "Client fidèle"))
            c.execute("INSERT INTO reservations(name, phone, title, qty, date, status, note) VALUES(?,?,?,?,?,?,?)",
                      ("Marie Martin", "0699887766", "Chants de victoire", 1, date.today().isoformat(), "En attente", "En attente"))

        with db.tx(immediate=True) as c:
            cleaned = db.clean_gdpr_reservations(c, days_retention=90)
            self.assertEqual(cleaned, 1)

            # Vérifier la réservation servie ancienne : téléphone effacé, nom anonymisé
            r1 = c.execute("SELECT * FROM reservations WHERE title=?", ("Bible d'étude",)).fetchone()
            self.assertIsNone(r1["phone"])
            self.assertTrue(r1["name"].startswith("Client RGPD #"))
            self.assertIn("RGPD", r1["note"])

            # Vérifier la réservation en attente récente : coordonnées conservées
            r2 = c.execute("SELECT * FROM reservations WHERE title=?", ("Chants de victoire",)).fetchone()
            self.assertEqual(r2["phone"], "0699887766")
            self.assertEqual(r2["name"], "Marie Martin")

    def test_gdpr_endpoints(self):
        """Vérifie les endpoints /api/gdpr/info et /api/gdpr/cleanup directement."""
        data = gdpr_info()
        self.assertEqual(data["status"], "CONFORME")
        self.assertIn("RGPD", data["framework"])

        req = FakeRequest("127.0.0.1", user="Admin")
        cleanup_data = gdpr_cleanup(req, days=90)
        self.assertTrue(cleanup_data["ok"])
        self.assertIn("anonymized", cleanup_data)


if __name__ == "__main__":
    unittest.main()
