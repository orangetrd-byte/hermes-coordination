import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HERMES_CHANNEL_HOST", "127.0.0.1")
os.environ.setdefault("HERMES_CHANNEL_PORT", "3444")
os.environ.setdefault("HERMES_CHANNEL_PIN", "test-pin")

import relay


class RelayApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp.name)
        self.original_data = relay.DATA
        self.original_backup = relay.BACKUP
        relay.DATA = self.temp_path / "channel.json"
        relay.BACKUP = self.temp_path / "channel.json.bak"
        relay.DATA.write_text(
            json.dumps(
                {
                    "agents": [{"name": "Hermes", "role": "orchestrator"}],
                    "messages": [],
                    "meta": {"responded": [], "claims": {}},
                }
            ),
            encoding="utf-8",
        )
        self.server = None
        self.thread = None
        self.start_server()

    def tearDown(self):
        self.stop_server()
        relay.DATA = self.original_data
        relay.BACKUP = self.original_backup
        self.temp.cleanup()

    def start_server(self):
        self.server = relay.HTTPServer(("127.0.0.1", 0), relay.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def stop_server(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
            self.server = None

    def request(self, method, path, body=None, pin="test-pin"):
        payload = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.base_url + path,
            data=payload,
            method=method,
            headers={"Content-Type": "application/json", "X-Channel-PIN": pin},
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, json.loads(exc.read())
            finally:
                exc.close()

    def post_source(self, content="source"):
        status, message = self.request(
            "POST",
            "/api/messages",
            {"from": "Hermes", "to": "all", "content": content},
        )
        self.assertEqual(status, 200)
        return message

    def test_claim_and_reply_are_exclusive_and_persist(self):
        source = self.post_source()
        status, _ = self.request(
            "POST", "/api/claim", {"source_id": source["id"], "worker": "one"}
        )
        self.assertEqual(status, 200)
        status, _ = self.request(
            "POST", "/api/claim", {"source_id": source["id"], "worker": "two"}
        )
        self.assertEqual(status, 409)

        reply = {
            "source_id": source["id"],
            "worker": "one",
            "from": "Ollama",
            "to": "Hermes",
            "content": "reply",
        }
        status, stored = self.request("POST", "/api/reply", reply)
        self.assertEqual(status, 200)
        self.assertEqual(stored["in_reply_to"], source["id"])
        status, _ = self.request("POST", "/api/reply", reply)
        self.assertEqual(status, 409)

        self.stop_server()
        self.start_server()
        status, messages = self.request("GET", "/api/messages")
        self.assertEqual(status, 200)
        replies = [item for item in messages if item.get("in_reply_to") == source["id"]]
        self.assertEqual(len(replies), 1)

    def test_concurrent_posts_do_not_lose_messages(self):
        def submit(number):
            return self.request(
                "POST",
                "/api/messages",
                {"from": "Hermes", "to": "all", "content": f"message-{number}"},
            )[0]

        with ThreadPoolExecutor(max_workers=8) as pool:
            statuses = list(pool.map(submit, range(25)))
        self.assertEqual(statuses, [200] * 25)
        stored = json.loads(relay.DATA.read_text(encoding="utf-8"))
        self.assertEqual(len(stored["messages"]), 25)
        self.assertEqual(len({item["id"] for item in stored["messages"]}), 25)

    def test_put_is_locked_atomic_and_creates_backup(self):
        source = self.post_source()
        status, result = self.request(
            "PUT",
            "/api/messages",
            {"id": source["id"], "status": "archived"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["message"]["status"], "archived")
        backup = json.loads(relay.BACKUP.read_text(encoding="utf-8"))
        previous = next(item for item in backup["messages"] if item["id"] == source["id"])
        self.assertEqual(previous["status"], "open")

    def test_corrupt_database_is_preserved(self):
        corrupt = b'{"messages": ['
        relay.DATA.write_bytes(corrupt)
        status, body = self.request("GET", "/api/messages")
        self.assertEqual(status, 500)
        self.assertEqual(body["error"], "database unavailable")
        self.assertEqual(relay.DATA.read_bytes(), corrupt)

    def test_failed_replace_preserves_database(self):
        original = relay.DATA.read_bytes()
        updated = json.loads(original)
        updated["messages"].append({"id": 1, "content": "not committed"})
        real_replace = relay.os.replace

        def replace(source, destination):
            if Path(destination) == relay.DATA:
                raise OSError("simulated replace failure")
            return real_replace(source, destination)

        with mock.patch.object(relay.os, "replace", side_effect=replace):
            with self.assertRaises(OSError):
                relay.write_db(updated)
        self.assertEqual(relay.DATA.read_bytes(), original)
        self.assertFalse(list(self.temp_path.glob(".*.tmp")))


if __name__ == "__main__":
    unittest.main()
