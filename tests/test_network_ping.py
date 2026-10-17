import unittest
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.main import ping

class TestNetworkPing(unittest.TestCase):
    def test_ping_endpoint(self):
        res = ping()
        self.assertTrue(res["ok"])
        self.assertIn("host", res)
        self.assertIn("mdns_host", res)
        self.assertIn("ips", res)
        self.assertIn("time", res)
        self.assertIsInstance(res["ips"], list)

if __name__ == "__main__":
    unittest.main()
