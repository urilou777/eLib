import os
import unittest
from types import SimpleNamespace

from fastapi import HTTPException
from starlette.datastructures import Headers

from app import db, security
from app.routers.books import book_enrich
from app.schemas import BookEnrichIn


class FakeRequest:
    headers = Headers({"X-User": "Test"})
    query_params = {}
    state = SimpleNamespace(role="desk", device=None)


class TestBookEnrichment(unittest.TestCase):
    def setUp(self):
        self.test_db = os.path.join(db.DATA_DIR, "test_book_enrichment.db")
        self.orig_db = db.DB_PATH
        db.DB_PATH = self.test_db
        db.init()

    def tearDown(self):
        db.DB_PATH = self.orig_db
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self.test_db + suffix)
            except FileNotFoundError:
                pass

    def add_book(self, code, title, **fields):
        with db.tx() as connection:
            cursor = connection.execute(
                "INSERT INTO books(code, title, author, publisher, price) VALUES(?,?,?,?,?)",
                (
                    code,
                    title,
                    fields.get("author"),
                    fields.get("publisher"),
                    fields.get("price", 0),
                ),
            )
            return cursor.lastrowid

    def test_enrich_fills_missing_fields_and_attaches_barcode(self):
        book_id = self.add_book("", "", publisher="Éditions existantes", price=15)

        result = book_enrich(
            book_id,
            BookEnrichIn(
                code="9781234567890",
                title="Titre reconnu",
                author="Autrice reconnue",
                publisher="Nouvel éditeur",
                price=20,
            ),
            FakeRequest(),
        )

        self.assertEqual(result["updated"], ["code", "title", "author"])
        self.assertEqual(result["book"]["code"], "9781234567890")
        self.assertEqual(result["book"]["title"], "Titre reconnu")
        self.assertEqual(result["book"]["author"], "Autrice reconnue")
        self.assertEqual(result["book"]["publisher"], "Éditions existantes")
        self.assertEqual(result["book"]["price"], 15)
        with db.tx() as connection:
            audit = connection.execute(
                "SELECT action, target_type FROM audit_logs WHERE target_id=? ORDER BY id DESC LIMIT 1",
                (book_id,),
            ).fetchone()
        self.assertEqual((audit["action"], audit["target_type"]), ("UPDATE", "book"))

    def test_enrich_rejects_barcode_owned_by_another_book(self):
        book_id = self.add_book("", "")
        self.add_book("9781234567890", "Autre livre")

        with self.assertRaises(HTTPException) as raised:
            book_enrich(
                book_id,
                BookEnrichIn(code="9781234567890", title="Titre reconnu"),
                FakeRequest(),
            )

        self.assertEqual(raised.exception.status_code, 409)
        with db.tx() as connection:
            book = connection.execute(
                "SELECT code, title FROM books WHERE id=?", (book_id,)
            ).fetchone()
        self.assertEqual((book["code"], book["title"]), ("", ""))

    def test_enrich_requires_a_title_for_an_incomplete_record(self):
        book_id = self.add_book("9781234567890", "")

        with self.assertRaises(HTTPException) as raised:
            book_enrich(book_id, BookEnrichIn(), FakeRequest())

        self.assertEqual(raised.exception.status_code, 422)

    def test_enrichment_endpoint_is_mobile_authenticated_not_public(self):
        path = "/api/books/12/enrich"
        self.assertTrue(security._match(security.MOBILE, "POST", path))
        self.assertFalse(security._match(security.PUBLIC, "POST", path))


if __name__ == "__main__":
    unittest.main()
