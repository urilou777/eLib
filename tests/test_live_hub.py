"""Tests unitaires pour le LiveHub et la régie des paniers en direct."""
import unittest
import time
from app.main import live_hub, ActiveBasketIn, ActiveBasketItem, update_active_basket, delete_active_basket, get_live_baskets
from starlette.datastructures import Headers


class FakeRequest:
    def __init__(self, host="127.0.0.1"):
        self.headers = Headers()
        self.client = type("Client", (), {"host": host})()


class TestLiveHub(unittest.TestCase):
    def setUp(self):
        live_hub.active_baskets.clear()

    def test_basket_lifecycle(self):
        # 1. Mise à jour panier (articles scannés)
        live_hub.update_basket("dev1", {
            "device_id": "dev1",
            "device_name": "iPhone Sophie",
            "user_name": "Sophie",
            "total": 24.50,
            "qty": 2,
            "items": [{"title": "Livre Test", "qty": 2, "price": 12.25}]
        })
        baskets = live_hub.get_active_baskets()
        self.assertEqual(len(baskets), 1)
        self.assertEqual(baskets[0]["user_name"], "Sophie")
        self.assertEqual(baskets[0]["qty"], 2)
        self.assertEqual(baskets[0]["status"], "scanning")

        # 2. Vidage panier : le mobile reste connecté et actif avec panier à 0
        live_hub.remove_basket("dev1", action={"type": "cart_cleared"})
        baskets_cleared = live_hub.get_active_baskets()
        self.assertEqual(len(baskets_cleared), 1)
        self.assertEqual(baskets_cleared[0]["qty"], 0)
        self.assertEqual(baskets_cleared[0]["status"], "connected")
        self.assertEqual(baskets_cleared[0]["state"], "active")

        # 3. Fermeture de session explicite : déconnexion complète
        live_hub.remove_basket("dev1", action={"type": "session_closed"})
        baskets_after = live_hub.get_active_baskets()
        self.assertEqual(len(baskets_after), 0)

    def test_basket_functions(self):
        req = FakeRequest("192.168.1.50")
        b_in = ActiveBasketIn(
            user_name="Marc",
            total=35.0,
            qty=3,
            items=[ActiveBasketItem(title="Guide de prière", qty=3, price=11.66)]
        )
        res = update_active_basket(b_in, req)
        self.assertEqual(res, {"ok": True})

        all_baskets = get_live_baskets()
        self.assertIn("baskets", all_baskets)
        self.assertTrue(any(b["user_name"] == "Marc" for b in all_baskets["baskets"]))

        # Vidage panier : le terminal reste connecté
        del_res = delete_active_basket(req, reason="cart_cleared")
        self.assertEqual(del_res, {"ok": True})
        rem_baskets = get_live_baskets()["baskets"]
        self.assertEqual(len(rem_baskets), 1)
        self.assertEqual(rem_baskets[0]["qty"], 0)

        # Déconnexion de session : terminal retiré
        close_res = delete_active_basket(req, reason="session_closed")
        self.assertEqual(close_res, {"ok": True})
        self.assertEqual(len(get_live_baskets()["baskets"]), 0)

    def test_out_of_stock_rejected(self):
        from app import db
        from app.main import AllocIn
        from pydantic import ValidationError

        # 1. Validation Pydantic
        with self.assertRaises(ValidationError):
            AllocIn(book_id=1, lot_id=None, qty=1)

        # 2. Rejet en base de données
        with db.tx() as c:
            with self.assertRaises(ValueError):
                db._insert_alloc(c, line_id=1, book_id=1, lot_id=None, qty=1, unit_rev=10.0, day="2026-10-17")


if __name__ == "__main__":
    unittest.main()
