import os
import sqlite3
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

    def test_legacy_device_database_is_backed_up_before_column_migration(self):
        database_path = os.path.join(self.temp_dir.name, "devices.db")
        connection = sqlite3.connect(database_path)
        try:
            connection.execute(
                "CREATE TABLE devices(id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "token_hash TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL, "
                "last_seen TEXT, last_ip TEXT, revoked INTEGER NOT NULL DEFAULT 0)"
            )
            connection.execute(
                "INSERT INTO devices(name, token_hash, created_at) VALUES('Phone', 'hash', 'today')"
            )
            connection.commit()
        finally:
            connection.close()

        with patch.object(security, "DEVICES_DB", database_path), patch.object(
            security.db, "DATA_DIR", self.temp_dir.name
        ):
            with security._dev() as migrated:
                columns = {row["name"] for row in migrated.execute("PRAGMA table_info(devices)")}
                self.assertIn("device_key", columns)
                self.assertIn("cashier_name", columns)
            backups = [
                name
                for name in os.listdir(os.path.join(self.temp_dir.name, "sauvegardes"))
                if name.startswith("devices_pre_migration_") and name.endswith(".db")
            ]
            self.assertEqual(len(backups), 1)
            backup = sqlite3.connect(os.path.join(self.temp_dir.name, "sauvegardes", backups[0]))
            try:
                row = backup.execute("SELECT name, token_hash FROM devices").fetchone()
                self.assertEqual(row, ("Phone", "hash"))
            finally:
                backup.close()

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
