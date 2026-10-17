import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.main import book_stats
from fastapi import HTTPException

class TestBookStats(unittest.TestCase):
    def test_book_stats_success(self):
        # Book 4 has sales in DB
        data = book_stats(4)
        self.assertEqual(data["book"]["id"], 4)
        self.assertIn("title", data["book"])
        self.assertIn("kpis", data)
        self.assertGreaterEqual(data["kpis"]["total_sold"], 1)
        self.assertGreaterEqual(data["kpis"]["total_revenue"], 1.0)
        self.assertIn("demographics", data)
        self.assertIn("gender", data["demographics"])
        self.assertIn("age_groups", data["demographics"])
        self.assertIn("star", data["demographics"])
        self.assertIsInstance(data["recent_sales"], list)

    def test_book_stats_pack(self):
        # Pack 57
        data = book_stats(57)
        self.assertEqual(data["book"]["id"], 57)
        self.assertTrue(data["book"]["is_pack"])

    def test_book_stats_not_found(self):
        with self.assertRaises(HTTPException) as ctx:
            book_stats(999999)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_mobile_security_allows_stats(self):
        from app.security import _match, MOBILE
        self.assertTrue(_match(MOBILE, "GET", "/api/books/4/stats"))
        self.assertTrue(_match(MOBILE, "GET", "/api/books/57/stats"))
        self.assertFalse(_match(MOBILE, "POST", "/api/books/4/stats"))

if __name__ == "__main__":
    unittest.main()
