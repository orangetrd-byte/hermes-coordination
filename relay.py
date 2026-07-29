#!/usr/bin/env python3
import json, os, ssl, datetime, urllib.parse, tempfile, subprocess, threading, socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "channel.json"
LOCK = threading.Lock()
PORT = int(os.environ["HERMES_CHANNEL_PORT"])
HOST = os.environ["HERMES_CHANNEL_HOST"]
PIN = os.environ["HERMES_CHANNEL_PIN"]
CERT = BASE / "server.crt"
KEY = BASE / "server.key"

def read_db():
    try:
        return json.loads(DATA.read_text())
    except Exception:
        fallback = {"agents": [], "messages": [], "meta": {}}
        DATA.write_text(json.dumps(fallback, indent=2))
        return fallback


def write_db(data):
    tmp = DATA.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(DATA)


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
        if p == "/api/agents":
            return _json(self, read_db()["agents"])
        if p == "/api/messages":
            return _json(self, read_db().get("messages", []))
        return self.serve_static()

    def do_POST(self):
        length = int(self.headers.get("content-length", 0))
        if length > 65536:
            return _badge(self, 413, "payload too large")
        body_raw = self.rfile.read(length)
        try:
            body = json.loads(body_raw)
        except Exception:
            return _badge(self, 400, "invalid json")

        req_pin = self.headers.get("X-Channel-PIN")
        if req_pin != PIN:
            return _badge(self, 401, "PIN required or invalid")

        p = self.path.split("?")[0]

        if p == "/api/messages":
            for k in ("from", "to", "content"):
                if k not in body:
                    return _badge(self, 400, f"missing {k}")
            with LOCK:
                data = read_db()
                msg = {
                    "id": int(datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S%f")),
                    "ts": datetime.datetime.utcnow().isoformat() + "Z",
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

        if p == "/api/reply":
            for k in ("source_id", "from", "to", "content"):
                if k not in body:
                    return _badge(self, 400, f"missing {k}")
            source_id = body["source_id"]
            with LOCK:
                data = read_db()
                responded = set(tuple(x) if isinstance(x, list) else x for x in data.get("meta", {}).get("responded", []))
                if source_id in responded:
                    return _badge(self, 409, "source already handled")
                replied = {
                    "id": int(datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S%f")),
                    "ts": datetime.datetime.utcnow().isoformat() + "Z",
                    "from": str(body["from"]),
                    "to": str(body["to"]),
                    "type": body.get("type", "chat"),
                    "content": str(body["content"]),
                    "status": body.get("status", "open"),
                    "assigned_to": "",
                    "in_reply_to": source_id,
                }
                data["messages"].append(replied)
                responded.add(source_id)
                data.setdefault("meta", {})["responded"] = list(responded)
                write_db(data)
            return _json(self, replied)

        return _badge(self, 404, "not found")

    def do_PUT(self):
        if self.path != "/api/messages":
            return _badge(self, 404, "not found")
        req_pin = self.headers.get("X-Channel-PIN")
        if req_pin != PIN:
            return _badge(self, 401, "PIN required or invalid")
        length = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(length))
        data = read_db()
        msgs = data.get("messages", [])
        target_id = body.get("id")
        for m in msgs:
            if m.get("id") == target_id:
                m["status"] = body.get("status", m.get("status"))
                m["assigned_to"] = body.get("assigned_to", m.get("assigned_to"))
                m["content"] = body.get("content", m.get("content"))
                write_db(data)
                return _json(self, {"ok": True, "message": m})
        return _badge(self, 404, "message not found")

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
