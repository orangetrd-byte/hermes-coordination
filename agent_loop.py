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

# Burst-test mode: limit replies per run
_BURST_REPLY_LIMIT = int(os.environ.get("HERMES_BURST_REPLY_LIMIT", "0"))


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
    kind = _kind(message)
    reply_type = kind if kind in {"chat", "assign", "status", "done", "yield", "inference"} else "chat"
    text = ""
    if reply_type == "inference":
        text = ollama_reply_inline(content, sender)
    elif reply_type == "assign":
        text = f"Acknowledged: {content}."
    elif reply_type == "status":
        text = "Idle, ready for assignment."
    elif reply_type == "done":
        text = "Marked done."
    elif reply_type == "yield":
        text = "Yield acknowledged."
    else:
        text = content or "I'm here."
    return {
        "from": "Ollama",
        "to": sender or "all",
        "type": reply_type,
        "content": text,
        "status": reply_type if reply_type not in {"assign", "status", "done", "yield", "inference"} else "open",
        "assigned_to": sender if reply_type == "assign" else "",
    }


def ollama_reply_inline(content, sender):
    out = ollama_reply(content, sender, retries=2)
    out.pop("assigned_to", None)
    return out


def ollama_reply(content, sender, retries=2):
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
    text = ""
    for attempt in range(retries + 1):
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
            if text:
                break
        except Exception as e:
            print("[ollama_error attempt]", attempt + 1, e)
    
    if not text:
        text = "Inference failed after retries; will retry on next message."
    return {
        "from": "Ollama",
        "to": sender or "all",
        "type": "chat",
        "content": text,
        "status": "open",
    }


def _kind(message):
    return (message.get("type") or "chat").lower()

def process_once():
    code, raw = api("/api/messages")
    if code != 200:
        print("[list_failed]", code)
        return None
    msgs = json.loads(raw)
    if not msgs:
        return None
    sent = 0
    for recent in msgs:
        mid = recent.get("id")
        sender = recent.get("from", "")
        kind = _kind(recent)
        if not mid:
            continue
        if kind in BLACKLISTED_TYPE:
            continue
        if sender not in ALLOWED_SENDERS:
            continue
        if kind in {"assign", "status", "done", "chat", "yield", "inference"}:
            reply = build_reply(recent)
        else:
            continue
        if not reply.get("content"):
            continue
        claim_payload = {"source_id": mid, "worker": WORKER_ID}
        ccode, craw = api("/api/claim", claim_payload, method="POST")
        if ccode == 409:
            continue
        if ccode != 200:
            print("[claim_failed]", ccode, craw[:120] if isinstance(craw, str) else craw)
            continue
        reply_payload = {
            "source_id": mid,
            "worker": WORKER_ID,
            "from": reply.get("from", "Ollama"),
            "to": reply.get("to", "all"),
            "type": reply.get("type", kind),
            "content": reply.get("content", ""),
            "status": reply.get("status") or reply.get("type") or "open",
        }
        code2, raw2 = api("/api/reply", reply_payload, method="POST")
        if code2 == 200:
            print("[send]", reply_payload["from"], "->", reply_payload["to"], reply_payload["content"][:80])
            sent += 1
            if _BURST_REPLY_LIMIT and sent >= _BURST_REPLY_LIMIT:
                return reply
            continue
        if code2 == 409:
            continue
        print("[send_failed]", code2, raw2)
        return None
    return None


def main():
    print(
        f"[agent_loop] started model={OLLAMA_MODEL} interval={POLL_INTERVAL}s"
    )
    while True:
        try:
            process_once()
        except Exception as e:
            print("[agent_loop_error]", e)
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
