import hashlib
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import updater


class TestUpdater(unittest.TestCase):
    def test_version_tuple_accepts_release_tag_prefix(self):
        self.assertEqual(updater._version_tuple("v1.12.3"), (1, 12, 3))

    def test_version_tuple_rejects_non_stable_versions(self):
        with self.assertRaises(ValueError):
            updater._version_tuple("v1.2.3-rc1")

    def test_latest_release_returns_stable_x86_assets(self):
        release = {
            "tag_name": "v1.2.3",
            "draft": False,
            "prerelease": False,
            "assets": [
                {
                    "name": "eLib.exe",
                    "size": 100,
                    "browser_download_url": "https://github.com/urilou777/eLib/releases/download/v1.2.3/eLib.exe",
                    "digest": "sha256:" + "a" * 64,
                },
                {
                    "name": "eLib.exe.sha256",
                    "size": 76,
                    "browser_download_url": "https://github.com/urilou777/eLib/releases/download/v1.2.3/eLib.exe.sha256",
                },
            ],
        }
        with patch.object(updater, "_request", return_value=io.BytesIO(json.dumps(release).encode())):
            latest = updater.get_latest_release()
        self.assertEqual(latest["version"], "1.2.3")
        self.assertEqual(latest["size"], 100)

    def test_latest_release_ignores_prereleases(self):
        release = {
            "tag_name": "v9.9.9",
            "draft": False,
            "prerelease": True,
            "assets": [],
        }
        with patch.object(updater, "_request", return_value=io.BytesIO(json.dumps(release).encode())):
            self.assertIsNone(updater.get_latest_release())

    def test_checksum_file_accepts_sha256sum_format(self):
        response = io.BytesIO(b"a" * 64 + b"  eLib.exe\n")
        with patch.object(updater, "_request", return_value=response):
            self.assertEqual(
                updater._read_expected_digest(
                    "https://github.com/urilou777/eLib/releases/download/v1.2.3/eLib.exe.sha256"
                ),
                "a" * 64,
            )

    def test_checksum_file_rejects_other_asset_names(self):
        response = io.BytesIO(b"a" * 64 + b"  other.exe\n")
        with patch.object(updater, "_request", return_value=response):
            with self.assertRaises(ValueError):
                updater._read_expected_digest(
                    "https://github.com/urilou777/eLib/releases/download/v1.2.3/eLib.exe.sha256"
                )

    def test_release_download_verifies_hash_and_x86_machine(self):
        executable = bytearray(70)
        executable[:2] = b"MZ"
        struct.pack_into("<I", executable, 0x3C, 64)
        executable[64:68] = b"PE\0\0"
        struct.pack_into("<H", executable, 68, 0x014C)
        payload = bytes(executable)
        release = {
            "checksum_url": "https://github.com/urilou777/eLib/releases/download/v1.2.3/eLib.exe.sha256",
            "download_url": "https://github.com/urilou777/eLib/releases/download/v1.2.3/eLib.exe",
            "api_digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
        }
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "eLib.exe"
            with patch.object(updater, "_read_expected_digest", return_value=hashlib.sha256(payload).hexdigest()), patch.object(
                updater, "_request", return_value=io.BytesIO(payload)
            ):
                updater._download_release(release, destination)
            self.assertEqual(destination.read_bytes(), payload)

    def test_release_download_rejects_wrong_hash(self):
        release = {
            "checksum_url": "https://github.com/urilou777/eLib/releases/download/v1.2.3/eLib.exe.sha256",
            "download_url": "https://github.com/urilou777/eLib/releases/download/v1.2.3/eLib.exe",
            "api_digest": None,
            "size": 4,
        }
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "eLib.exe"
            with patch.object(updater, "_read_expected_digest", return_value="0" * 64), patch.object(
                updater, "_request", return_value=io.BytesIO(b"bad!")
            ):
                with self.assertRaises(ValueError):
                    updater._download_release(release, destination)
            self.assertFalse(destination.exists())

    def test_install_script_quotes_paths_for_powershell(self):
        script = updater._install_script(
            r"C:\Users\O'Brien\eLib.exe",
            r"C:\Users\O'Brien\data\updates\eLib.exe",
            123,
        )
        self.assertIn("'C:\\Users\\O''Brien\\eLib.exe'", script)

    def test_asset_url_rejects_other_hosts(self):
        with self.assertRaises(ValueError):
            updater._validate_asset_url("https://evil.example/eLib.exe")


if __name__ == "__main__":
    unittest.main()
