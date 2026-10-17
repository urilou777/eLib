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
        # 1. Mise à jour panier
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

        # 2. Retrait panier
        live_hub.remove_basket("dev1")
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

        del_res = delete_active_basket(req)
        self.assertEqual(del_res, {"ok": True})
        self.assertEqual(len(get_live_baskets()["baskets"]), 0)


if __name__ == "__main__":
    unittest.main()
