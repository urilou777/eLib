import os
import tempfile
import unittest
from unittest.mock import patch

from app import security


class TestDevicePairing(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_devices_db = security.DEVICES_DB
        security.DEVICES_DB = os.path.join(self.temp_dir.name, "devices.db")

    def tearDown(self):
        security.DEVICES_DB = self.original_devices_db
        self.temp_dir.cleanup()

    def redeem(self, device_key=None, previous_token=None):
        with patch.object(security, "_blocked", return_value=False), patch.object(
            security, "_consume_code", return_value=True
        ):
            return security.redeem_pairing(
                "valid-pairing-code",
                "Phone",
                "127.0.0.1",
                device_key,
                previous_token,
            )

    def test_repairing_device_revokes_previous_token(self):
        key = "device-key-0123456789abcdef"
        previous = self.redeem(device_key=key)
        current = self.redeem(device_key=key, previous_token=previous)

        devices = security.list_devices()
        self.assertEqual(len(devices), 1)
        self.assertNotEqual(previous, current)
        self.assertEqual(devices[0]["name"], "Phone")

    def test_distinct_devices_remain_authorized(self):
        self.redeem(device_key="device-key-one-012345")
        self.redeem(device_key="device-key-two-012345")

        self.assertEqual(len(security.list_devices()), 2)

    def test_active_device_lists_selected_cashier(self):
        token = self.redeem(device_key="device-key-cashier-012345")
        with security._dev() as connection:
            device_id = connection.execute(
                "SELECT id FROM devices WHERE token_hash=?",
                (security._hash(token),),
            ).fetchone()["id"]

        security.update_device_cashier(device_id, "Sophie")

        self.assertEqual(security.list_devices()[0]["cashier_name"], "Sophie")


if __name__ == "__main__":
    unittest.main()
