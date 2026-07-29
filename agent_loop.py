#!/usr/bin/env python3
r"""
Hermes Agent Loop
Polls /api/messages, and when a non-agent message appears,
builds one reply and posts it.
"""
import json, os, socket, time, urllib.request, urllib.error, ssl
from pathlib import Path

BASE = Path(__file__).resolve().parent
PORT = int(os.environ["HERMES_CHANNEL_PORT"])
HOST = os.environ["HERMES_CHANNEL_HOST"]
PIN = os.environ["HERMES_CHANNEL_PIN"]
OLLAMA_HOST = os.environ.get("HERMES_OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("HERMES_OLLAMA_MODEL", "deepseek-coder-v2:16b")
POLL_INTERVAL = float(os.environ.get("HERMES_POLL_INTERVAL", "2.0"))
RESPOND_COOLDOWN = int(os.environ.get("HERMES_RESPOND_COOLDOWN", "30"))
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"

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
    code, raw = api("/api/messages")
    if code != 200:
        print("[list_failed]", code, raw)
        return None
    msgs = json.loads(raw)
    if not msgs:
        return None
    recent = msgs[-1]
    mid = recent.get("id")
    sender = recent.get("from", "")
    kind = (recent.get("status") or recent.get("type") or "chat").lower()
    if not mid:
        return None
    if kind in BLACKLISTED_TYPE:
        print("[skip] type", kind)
        return None
    if sender not in ALLOWED_SENDERS:
        print("[skip] sender", sender)
        return None
    claim_code, claim_raw = api(
        "/api/claim",
        {"source_id": mid, "worker": WORKER_ID},
        method="POST",
    )
    if claim_code == 409:
        print("[skip] already_claimed", mid)
        return None
    if claim_code != 200:
        print("[claim_failed]", claim_code, claim_raw)
        return None
    reply = build_reply(recent)
    if not reply.get("content"):
        return None
    code2, raw2 = api("/api/reply", {
        "source_id": mid,
        "worker": WORKER_ID,
        "from": reply.get("from", "Ollama"),
        "to": reply.get("to", "all"),
        "type": reply.get("type", "chat"),
        "content": reply.get("content", ""),
        "status": reply.get("status", "open"),
    }, method="POST")
    if code2 == 200:
        print("[send]", reply.get("from"), "->", reply.get("to"), reply.get("content")[:80])
        return reply
    if code2 == 409:
        print("[skip] already_handled", mid)
        return None
    print("[send_failed]", code2, raw2)
    return None


def main():
    print(
        f"[agent_loop] started port={PORT} pin={PIN} model={OLLAMA_MODEL} interval={POLL_INTERVAL}s"
    )
    while True:
        try:
            process_once()
        except Exception as e:
            print("[agent_loop_error]", e)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
