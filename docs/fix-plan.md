# Hermes Coordination — Fix Plan

## Goal

Make Hermes Coordination a reliable HTTPS message channel where the UI, relay, and agent loop use one configuration, messages persist safely, and each eligible message receives exactly one agent response.

## Phase 1 — Standardize configuration

- Use HTTPS and port 3444 everywhere.
- Update:
  - Start-HermesChannel.ps1
  - restart-relay.ps1
  - Open-HermesChannel.bat
  - firewall-8787.bat → rename for port 3444
- Centralize host, port, PIN, certificate paths, and Ollama model.
- Remove hard-coded PIN 070112; require an environment variable or protected local configuration file.
- Fail startup with a clear message when configuration is missing.

Acceptance:
- Every launcher opens the same HTTPS address.
- No active reference to port 8787 remains.

## Phase 2 — Repair startup behavior

- If port 3444 already has the Hermes relay listening, reuse it instead of starting another process.
- Verify the listener belongs to Hermes before trusting it.
- Start both relay.py and agent_loop.py.
- Poll /api/health until ready instead of sleeping for 700 ms.
- Detect early process exits and display the actual error.
- Open the browser only after the health check succeeds.
- Add clean shutdown/restart behavior.

Acceptance:
- Repeated launcher clicks produce only one relay and one agent loop.
- Browser never opens to a dead server.
- Restart reliably replaces both processes.

## Phase 3 — Make the relay the only database writer

- Remove all direct channel.json writes from agent_loop.py.
- Add relay endpoints for:
  - Health checks
  - Posting messages
  - Updating messages
  - Claiming a message for processing
  - Atomically posting a reply and marking its source handled
- Write JSON atomically using a temporary file and os.replace.
- Preserve the previous valid database if parsing or writing fails.
- Add a server-side lock around database operations.

Acceptance:
- Agent replies no longer disappear.
- Concurrent UI and agent-loop activity cannot corrupt or overwrite messages.

## Phase 4 — Fix agent processing

- Process every unhandled eligible message, not only messages[-1].
- Remove prime_once() behavior that silently skips the newest message.
- Add in_reply_to to replies.
- Enforce one reply per source message on the server.
- Either implement RESPOND_COOLDOWN or remove it.
- Record processing states: pending, claimed, completed, and failed.
- Retry temporary Ollama failures with a bounded retry count.
- Display permanent failures in the channel.
- Do not label Ollama responses as GPT or Codex unless those agents are genuinely connected.

Acceptance:
- Several rapidly submitted messages are all processed once.
- Restarting the agent loop does not duplicate or skip replies.
- Ollama failure produces a visible, actionable error.

## Phase 5 — Secure the relay

- Serve static files from an explicit allowlist or dedicated public directory.
- Never serve:
  - server.key
  - server.crt
  - channel.json
  - Python files
  - Configuration files
- Reject resolved paths outside the public directory.
- Validate JSON bodies and return controlled 400 responses.
- Limit request and message sizes.
- Validate sender, recipient, type, and status against allowed values.
- Prevent UI users from impersonating agents.
- Add PIN attempt throttling.
- Bind to 127.0.0.1 by default; require explicit configuration for LAN access.
- Document certificate installation for trusted LAN HTTPS.

Acceptance:
- Requests for sensitive files return 404.
- Path traversal attempts return 404.
- Invalid and oversized requests do not crash the server.
- Unauthorized users cannot post as Codex, GPT, Ollama, or Hermes.

## Phase 6 — Correct the UI

- Determine message appearance and filtering from type; use status only for lifecycle state.
- Make Chat, Assign, Status, Done, Yield, and Inference filters work.
- Make Clear either:
  - Hide archived messages, or
  - Use a true delete endpoint with confirmation.
- Show the empty state when no visible messages exist.
- Set the connection indicator green after successful requests and gray/red after failure.
- Preserve the selected sender, recipient, and filter during refresh.
- Display API errors instead of silently clearing the composer.
- Poll for updates without resetting filters or scrolling unnecessarily.
- Remove duplicate JavaScript by keeping one source of truth.

Acceptance:
- Filters return the expected messages.
- Archived messages disappear from the normal feed.
- Failed sends remain in the composer and show an error.
- New messages appear without resetting the interface.

## Phase 7 — Add verification

Create automated tests for:

- Correct and incorrect PINs
- Health endpoint
- Message creation and validation
- Atomic reply plus handled-state update
- Duplicate-response prevention
- Multiple queued messages
- Restart recovery
- Corrupt database recovery
- Static-file allowlist
- Path traversal rejection
- Private-key access rejection
- UI message-type filtering
- Archive visibility
- Port and protocol consistency

Final smoke test:

1. Start Hermes from the desktop shortcut.
2. Confirm one relay and one agent loop are running.
3. Connect through HTTPS.
4. Submit five messages rapidly.
5. Confirm five replies appear and persist.
6. Restart Hermes.
7. Confirm no messages disappear or receive duplicate replies.
8. Confirm server.key, channel.json, and traversal paths are inaccessible.
