#!/usr/bin/env python3
import datetime
import json
import os
import ssl
import tempfile
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "channel.json"
BACKUP = BASE / "channel.json.bak"
LOCK = threading.Lock()
PORT = int(os.environ["HERMES_CHANNEL_PORT"])
HOST = os.environ["HERMES_CHANNEL_HOST"]
PIN = os.environ["HERMES_CHANNEL_PIN"]
CLAIM_TTL = int(os.environ.get("HERMES_CLAIM_TTL", "300"))
CERT = BASE / "server.crt"
KEY = BASE / "server.key"


class DatabaseError(RuntimeError):
    pass


def read_db():
    try:
        data = json.loads(DATA.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatabaseError(f"database unavailable: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
        raise DatabaseError("database has an invalid structure")
    data.setdefault("agents", [])
    data.setdefault("meta", {})
    return data


def _atomic_write(path, payload):
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def write_db(data):
    payload = json.dumps(data, indent=2).encode("utf-8")
    if DATA.exists():
        _atomic_write(BACKUP, DATA.read_bytes())
    _atomic_write(DATA, payload)


def _find_message(data, message_id):
    return next((item for item in data["messages"] if item.get("id") == message_id), None)


def _read_body(handler):
    try:
        length = int(handler.headers.get("content-length", 0))
    except ValueError:
        raise ValueError("invalid content length")
    if length < 1:
        raise ValueError("request body required")
    if length > 65536:
        raise OverflowError("payload too large")
    try:
        body = json.loads(handler.rfile.read(length))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid json") from exc
    if not isinstance(body, dict):
        raise ValueError("json object required")
    return body


def _badge(self, code, msg):
    payload = json.dumps({"error": msg}).encode()
    self.send_response(code)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(payload)))
    self.end_headers()
    self.wfile.write(payload)

def _json(self, obj):
    payload = json.dumps(obj).encode()
    self.send_response(200)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(payload)))
    self.end_headers()
    self.wfile.write(payload)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            self.path = "/index.html"
            return self.serve_static("text/html")
        if p == "/api/health":
            return _json(self, {"ok": True})
        req_pin = self.headers.get("X-Channel-PIN")
        if req_pin != PIN:
            return _badge(self, 401, "PIN required or invalid")
        try:
            if p == "/api/agents":
                with LOCK:
                    agents = list(read_db()["agents"])
                return _json(self, agents)
            if p == "/api/messages":
                with LOCK:
                    messages = list(read_db()["messages"])
                return _json(self, messages)
        except DatabaseError as exc:
            self.log_error("%s", exc)
            return _badge(self, 500, "database unavailable")
        return self.serve_static()

    def do_POST(self):
        try:
            return self._do_POST()
        except (DatabaseError, OSError) as exc:
            self.log_error("POST failed: %s", exc)
            return _badge(self, 500, "database unavailable")

    def _do_POST(self):
        if self.headers.get("X-Channel-PIN") != PIN:
            return _badge(self, 401, "PIN required or invalid")
        try:
            body = _read_body(self)
        except OverflowError as exc:
            return _badge(self, 413, str(exc))
        except ValueError as exc:
            return _badge(self, 400, str(exc))

        p = self.path.split("?")[0]

        if p == "/api/messages":
            for k in ("from", "to", "content"):
                if k not in body:
                    return _badge(self, 400, f"missing {k}")
            with LOCK:
                data = read_db()
                msg = {
                    "id": int(datetime.datetime.now(datetime.UTC).strftime("%Y%m%d%H%M%S%f")),
                    "ts": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
                    "from": str(body["from"]),
                    "to": str(body["to"]),
                    "type": body.get("type", "chat"),
                    "content": str(body["content"]),
                    "status": body.get("status", "open"),
                    "assigned_to": body.get("assigned_to", ""),
                }
                data["messages"].append(msg)
                write_db(data)
            return _json(self, msg)

        if p == "/api/claim":
            for key in ("source_id", "worker"):
                if key not in body:
                    return _badge(self, 400, f"missing {key}")
            source_id = body["source_id"]
            worker = str(body["worker"])
            now = time.time()
            try:
                with LOCK:
                    data = read_db()
                    if not _find_message(data, source_id):
                        return _badge(self, 404, "source message not found")
                    meta = data.setdefault("meta", {})
                    if source_id in meta.setdefault("responded", []):
                        return _badge(self, 409, "source already handled")
                    claims = meta.setdefault("claims", {})
                    current = claims.get(str(source_id))
                    if current and current.get("expires_at", 0) > now:
                        return _badge(self, 409, "source already claimed")
                    claim = {
                        "worker": worker,
                        "claimed_at": now,
                        "expires_at": now + CLAIM_TTL,
                    }
                    claims[str(source_id)] = claim
                    write_db(data)
                return _json(self, {"ok": True, "claim": claim})
            except (DatabaseError, OSError) as exc:
                self.log_error("claim failed: %s", exc)
                return _badge(self, 500, "database unavailable")

        if p == "/api/reply":
            for k in ("source_id", "worker", "from", "to", "content"):
                if k not in body:
                    return _badge(self, 400, f"missing {k}")
            source_id = body["source_id"]
            worker = str(body["worker"])
            with LOCK:
                data = read_db()
                if not _find_message(data, source_id):
                    return _badge(self, 404, "source message not found")
                meta = data.setdefault("meta", {})
                responded = meta.setdefault("responded", [])
                if source_id in responded:
                    return _badge(self, 409, "source already handled")
                claims = meta.setdefault("claims", {})
                claim = claims.get(str(source_id))
                if not claim or claim.get("expires_at", 0) <= time.time():
                    return _badge(self, 409, "source is not claimed")
                if claim.get("worker") != worker:
                    return _badge(self, 409, "source claimed by another worker")
                replied = {
                    "id": int(datetime.datetime.now(datetime.UTC).strftime("%Y%m%d%H%M%S%f")),
                    "ts": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
                    "from": str(body["from"]),
                    "to": str(body["to"]),
                    "type": body.get("type", "chat"),
                    "content": str(body["content"]),
                    "status": body.get("status", "open"),
                    "assigned_to": "",
                    "in_reply_to": source_id,
                }
                data["messages"].append(replied)
                responded.append(source_id)
                claims.pop(str(source_id), None)
                write_db(data)
            return _json(self, replied)

        return _badge(self, 404, "not found")

    def do_PUT(self):
        if self.path != "/api/messages":
            return _badge(self, 404, "not found")
        if self.headers.get("X-Channel-PIN") != PIN:
            return _badge(self, 401, "PIN required or invalid")
        try:
            body = _read_body(self)
        except OverflowError as exc:
            return _badge(self, 413, str(exc))
        except ValueError as exc:
            return _badge(self, 400, str(exc))
        if "id" not in body:
            return _badge(self, 400, "missing id")
        try:
            with LOCK:
                data = read_db()
                message = _find_message(data, body["id"])
                if not message:
                    return _badge(self, 404, "message not found")
                message["status"] = body.get("status", message.get("status"))
                message["assigned_to"] = body.get("assigned_to", message.get("assigned_to"))
                message["content"] = body.get("content", message.get("content"))
                write_db(data)
            return _json(self, {"ok": True, "message": message})
        except (DatabaseError, OSError) as exc:
            self.log_error("PUT failed: %s", exc)
            return _badge(self, 500, "database unavailable")

    def serve_static(self, ctype=None):
        clean = self.path.split("?")[0].lstrip("/")
        if not clean or clean.endswith("/"):
            clean = "index.html"
        path = (BASE / clean).resolve()
        if not path.exists() or path.is_dir():
            return _badge(self, 404, "not found")
        ct = ctype or {
            ".html": "text/html",
            ".css": "text/css",
            ".js": "application/javascript",
            ".json": "application/json",
            ".png": "image/png",
            ".svg": "image/svg+xml",
        }.get(path.suffix.lower(), "application/octet-stream")
        payload = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

if __name__ == "__main__":
    if not CERT.exists() or not KEY.exists():
        raise SystemExit(f"Missing {CERT} / {KEY}. Generate self-signed cert first.")
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(CERT), str(KEY))
    httpd = HTTPServer((HOST, PORT), Handler)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    print(f"Serving HTTPS on {HOST}:{PORT}")
    httpd.serve_forever()
