import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from app import db


class TestDatabaseMigrationBackup(unittest.TestCase):
    def test_legacy_database_is_backed_up_before_baseline_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "librairie.db")
            connection = sqlite3.connect(database_path)
            try:
                connection.execute("CREATE TABLE legacy_data (value TEXT)")
                connection.execute("INSERT INTO legacy_data VALUES ('preserve me')")
                connection.commit()
            finally:
                connection.close()

            with patch.object(db, "DB_PATH", database_path), patch.object(db, "DATA_DIR", directory):
                db.init()
                connection = sqlite3.connect(database_path)
                try:
                    self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
                    self.assertEqual(
                        connection.execute(
                            "SELECT value FROM app_settings WHERE key='local_card_enabled'"
                        ).fetchone()[0],
                        "0",
                    )
                finally:
                    connection.close()
                backups = [
                    name
                    for name in os.listdir(os.path.join(directory, "sauvegardes"))
                    if name.startswith("librairie_pre_migration_") and name.endswith(".db")
                ]
                self.assertEqual(len(backups), 1)
                backup = sqlite3.connect(os.path.join(directory, "sauvegardes", backups[0]))
                try:
                    self.assertEqual(
                        backup.execute("SELECT value FROM legacy_data").fetchone()[0],
                        "preserve me",
                    )
                finally:
                    backup.close()

                db.init()
                backups_after_repeat = [
                    name
                    for name in os.listdir(os.path.join(directory, "sauvegardes"))
                    if name.startswith("librairie_pre_migration_") and name.endswith(".db")
                ]
                self.assertEqual(backups_after_repeat, backups)

    def test_registered_schema_migration_runs_once(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "librairie.db")
            connection = sqlite3.connect(database_path)
            try:
                connection.execute("CREATE TABLE legacy_data (value TEXT)")
                connection.execute("INSERT INTO legacy_data VALUES ('preserve me')")
                connection.execute("PRAGMA user_version=1")
                connection.commit()
            finally:
                connection.close()

            def migration_v2(connection):
                connection.execute("CREATE TABLE migration_marker (value TEXT)")
                connection.execute("INSERT INTO migration_marker VALUES ('v2')")

            with patch.object(db, "DB_PATH", database_path), patch.object(
                db, "DATA_DIR", directory
            ), patch.object(db, "LATEST_SCHEMA_VERSION", 2), patch.dict(
                db.SCHEMA_MIGRATIONS, {2: migration_v2}
            ):
                db.init()
                db.init()
                connection = sqlite3.connect(database_path)
                try:
                    self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
                    self.assertEqual(
                        connection.execute("SELECT COUNT(*) FROM migration_marker").fetchone()[0],
                        1,
                    )
                finally:
                    connection.close()


if __name__ == "__main__":
    unittest.main()
