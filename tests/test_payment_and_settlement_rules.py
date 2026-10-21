import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from starlette.requests import Request

from app import db
from app.routers import admin, reports, sales
from app.schemas import AllocIn, LineIn, LocalCardSettingIn, PaymentPartIn, SaleIn


class TestPaymentAndSettlementRules(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path_patch = patch.object(db, "DB_PATH", os.path.join(self.temp_dir.name, "librairie.db"))
        self.data_dir_patch = patch.object(db, "DATA_DIR", self.temp_dir.name)
        self.db_path_patch.start()
        self.data_dir_patch.start()
        db.init()
        with db.tx() as connection:
            self.cr_id = connection.execute(
                "SELECT id FROM owners WHERE LOWER(TRIM(name))='cité royale'"
            ).fetchone()["id"]
            self.local_id = connection.execute(
                "SELECT id FROM owners WHERE LOWER(TRIM(name))='icc rennes'"
            ).fetchone()["id"]
            connection.execute(
                "INSERT INTO books(id, code, title, price) VALUES(1, 'TEST-1', 'Livre test', 10)"
            )
            connection.execute(
                "INSERT INTO lots(id, book_id, owner_id, date, qty_in) VALUES(1, 1, ?, '2026-01-01', 20)",
                (self.cr_id,),
            )
            connection.execute(
                "INSERT INTO lots(id, book_id, owner_id, date, qty_in) VALUES(2, 1, ?, '2026-01-01', 20)",
                (self.local_id,),
            )

    def tearDown(self):
        self.db_path_patch.stop()
        self.data_dir_patch.stop()
        self.temp_dir.cleanup()

    @staticmethod
    def request():
        return Request({
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/sales",
            "root_path": "",
            "query_string": b"",
            "headers": [(b"x-user", b"Test")],
            "server": ("127.0.0.1", 8765),
            "client": ("127.0.0.1", 12345),
            "state": {"role": "desk"},
        })

    @staticmethod
    def sale(payment, lot_id, payments=None):
        return SaleIn(
            date="2026-02-01",
            payment=payment,
            payments=payments,
            lines=[
                LineIn(
                    book_id=1,
                    qty=1,
                    unit_price=10,
                    allocations=[AllocIn(book_id=1, lot_id=lot_id, qty=1)],
                )
            ],
        )

    def add_sale(self, sale):
        with patch.object(sales.live_hub, "broadcast"), patch.object(sales.live_hub, "remove_basket"):
            return sales.sale_add(sale, self.request())

    def test_cite_royale_cb_is_not_due_but_non_card_payment_remains_payable(self):
        self.add_sale(self.sale("CB", 1))
        self.add_sale(self.sale(
            "Paiement combiné",
            1,
            [
                PaymentPartIn(payment="CB", amount=6),
                PaymentPartIn(payment="Espèces", amount=4),
            ],
        ))

        summary = sales.treasury_summary()
        self.assertEqual(summary["cr_sales_total"], 20)
        self.assertEqual(summary["cr_due_to_paypal_total"], 4)
        test_balance = next(item for item in summary["user_balances"] if item["user_name"] == "Test")
        self.assertEqual(test_balance["cr_due_to_paypal"], 4)
        self.assertNotIn("cr_non_paypal_total", summary)

        cr_summary = next(item for item in sales.settlements() if item["id"] == self.cr_id)
        self.assertEqual(cr_summary["due"], 20)
        self.assertEqual(cr_summary["payable_due"], 4)
        self.assertEqual(cr_summary["remaining"], 4)
        self.assertEqual(reports.stats("2026-02-01", "2026-02-01")["kpi"]["due_open"], 4)

        with db.tx() as connection:
            connection.execute(
                "INSERT INTO settlements(owner_id, date, amount, note) VALUES(?, '2026-02-02', 4, 'Régularisé sur PayPal')",
                (self.cr_id,),
            )
        self.assertEqual(sales.treasury_summary()["cr_due_to_paypal_total"], 0)
        cr_summary = next(item for item in sales.settlements() if item["id"] == self.cr_id)
        self.assertEqual(cr_summary["remaining"], 0)
        self.assertEqual(reports.stats("2026-02-01", "2026-02-01")["kpi"]["due_open"], 0)

    def test_local_card_is_rejected_by_default_and_allowed_after_setting_change(self):
        with self.assertRaises(HTTPException) as raised:
            self.add_sale(self.sale("CB", 2))
        self.assertEqual(raised.exception.status_code, 400)

        with self.assertRaises(HTTPException):
            self.add_sale(self.sale(
                "Paiement combiné",
                2,
                [
                    PaymentPartIn(payment="CB", amount=5),
                    PaymentPartIn(payment="Espèces", amount=5),
                ],
            ))

        self.assertFalse(admin.get_options()["local_card_enabled"])
        admin.set_local_card_setting(LocalCardSettingIn(enabled=True), self.request())
        self.assertTrue(admin.get_options()["local_card_enabled"])
        self.add_sale(self.sale("CB", 2))
        with db.tx() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
