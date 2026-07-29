#!/usr/bin/env python3
r"""
Hermes Agent Loop
Polls /api/messages, and when a non-agent message appears,
builds one reply and posts it.
"""
import json, os, time, urllib.request, urllib.error, ssl
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "channel.json"
PORT = int(os.environ["HERMES_CHANNEL_PORT"])
HOST = os.environ["HERMES_CHANNEL_HOST"]
PIN = os.environ["HERMES_CHANNEL_PIN"]
OLLAMA_HOST = os.environ.get("HERMES_OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("HERMES_OLLAMA_MODEL", "deepseek-coder-v2:16b")
POLL_INTERVAL = float(os.environ.get("HERMES_POLL_INTERVAL", "2.0"))
RESPOND_COOLDOWN = int(os.environ.get("HERMES_RESPOND_COOLDOWN", "30"))

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

AGENTS = {
    "Hermes": {"role": "orchestrator", "color": "#2563eb"},
    "GPT": {"role": "coder", "color": "#10b981"},
    "Codex": {"role": "coder", "color": "#f59e0b"},
    "Ollama": {"role": "inference", "color": "#a78bfa"},
}

BLACKLISTED_FROM = {"Codex", "GPT"}
BLACKLISTED_TYPE = {"yield", "inference"}
ALLOWED_SENDERS = {"Hermes"}
RESPONDED_IDS = object()  # fake default


def api(path, data=None, method="GET"):
    url = f"https://{HOST}:{PORT}{path}"
    headers = {
        "Content-Type": "application/json",
        "X-Channel-PIN": PIN,
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=10) as r:
            raw = r.read().decode()
            return r.status, raw
    except urllib.error.HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode()
        except Exception:
            pass
        return e.code, raw
    except Exception as e:
        return 0, str(e)


def load_db():
    try:
        return json.loads(DATA.read_text())
    except Exception:
        return {"agents": list(AGENTS.values()), "messages": [], "meta": {"responded": []}}


def save_db(db):
    DATA.write_text(json.dumps(db, indent=2))


def responded_set(db):
    try:
        return set(tuple(x) if isinstance(x, list) else x for x in db.get("meta", {}).get("responded", []))
    except Exception:
        return set()


def mark_responded(db, mid):
    meta = db.setdefault("meta", {})
    responded = list(meta.get("responded", []))
    responded.append(mid)
    if len(responded) > 1000:
        responded = responded[-1000:]
    meta["responded"] = responded


def build_reply(message):
    sender = message.get("from", "")
    content = (message.get("content") or "").strip()
    kind = (message.get("status") or message.get("type") or "chat").lower()

    if kind == "status":
        return {
            "from": "Codex",
            "to": sender,
            "type": "status",
            "content": "Idle, ready for assignment.",
            "status": "open",
        }
    if kind == "assign":
        return {
            "from": "GPT",
            "to": sender,
            "type": "status",
            "content": f"Acknowledged: {content}.",
            "status": "open",
        }
    if kind == "done":
        return {
            "from": "GPT",
            "to": sender,
            "type": "done",
            "content": "Marked done.",
            "status": "done",
        }
    if kind == "yield":
        return {
            "from": "Ollama",
            "to": sender,
            "type": "yield",
            "content": "Yield acknowledged.",
            "status": "yield",
        }
    if kind == "inference":
        return ollama_reply(content, sender)
    return ollama_reply(content, sender)


def ollama_reply(content, sender):
    if not content:
        return {
            "from": "Ollama",
            "to": sender or "all",
            "type": "chat",
            "content": "I'm here.",
            "status": "open",
        }
    prompt = (
        "You are an assistant in a local agent coordination channel. "
        "Reply concisely and usefully. "
        f"User said: {content}"
    )
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": 1024, "num_predict": 128},
    }
    try:
        req = urllib.request.Request(
            f"{OLLAMA_HOST}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            result = json.loads(r.read().decode())
            text = (result.get("response") or "").strip()
    except Exception as e:
        print("[ollama_error]", e)
        text = "Local inference unavailable right now."

    return {
        "from": "Ollama",
        "to": sender or "all",
        "type": "chat",
        "content": text,
        "status": "open",
    }


def process_once():
    db = load_db()
    msgs = db.get("messages", [])
    if not msgs:
        return None
    recent = msgs[-1]
    ts = recent.get("ts")
    mid = recent.get("id")
    sender = recent.get("from", "")
    kind = (recent.get("status") or recent.get("type") or "chat").lower()
    if not ts:
        return None
    if mid is None:
        return None
    if kind in BLACKLISTED_TYPE:
        print("[skip] type", kind)
        return None
    if sender not in ALLOWED_SENDERS:
        print("[skip] sender", sender)
        return None
    responded = responded_set(db)
    if mid in responded:
        print("[skip] already_responded", mid)
        return None
    reply = build_reply(recent)
    if not reply.get("content"):
        return None
    code, raw = api("/api/messages", {
        "from": reply.get("from", "Ollama"),
        "to": reply.get("to", "all"),
        "type": reply.get("type", "chat"),
        "content": reply.get("content", ""),
        "status": reply.get("status", "open"),
        "assigned_to": "",
    }, method="POST")
    if code == 200:
        mark_responded(db, mid)
        save_db(db)
        print("[send]", reply.get("from"), "->", reply.get("to"), reply.get("content")[:80])
        return reply
    print("[send_failed]", code, raw)
    return None


def prime_once():
    db = load_db()
    msgs = db.get("messages", [])
    if msgs:
        mark_responded(db, msgs[-1].get("id"))
        save_db(db)


def main():
    print(
        f"[agent_loop] started port={PORT} pin={PIN} model={OLLAMA_MODEL} cooldown={RESPOND_COOLDOWN}s"
    )
    prime_once()
    while True:
        try:
            process_once()
        except Exception as e:
            print("[agent_loop_error]", e)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
