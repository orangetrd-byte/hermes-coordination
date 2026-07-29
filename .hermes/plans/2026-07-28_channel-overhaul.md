# Hermes Coordination Channel Overhaul Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Improve layout, usability, and intuitive use of the local coordination channel without changing its existing API shape.

**Architecture:** Keep the same lightweight backend + static frontend model. Frontend-only UX upgrade with semantic HTML, responsive layout, improved composer UX, and clearer message hierarchy. Minimal backend changes.

**Tech Stack:** Vanilla HTML/CSS/JS, Python HTTPServer backend unchanged in behavior.

---

## Current Context

- `C:\Users\Dad\Documents\HermesCoordination\relay.py` serves `/`, `/index.html`, `/api/agents`, `/api/messages`, `/api/messages` POST/PUT.
- `channel.json` stores agents and messages.
- `index.html` contains all UI + inline JS.
- Mobile currently cannot connect to LAN due to Python binding/firewall; UI should nonetheless be mobile-friendly when accessible.

## Proposed Approach

1. Separate the UI layout structure so it scales on mobile/desktop.
2. Make agents visually distinct and status-aware.
3. Improve the composer with inline validation, quick-select chips, and keyboard shortcuts.
4. Add message grouping by conversation and clearer timestamps.
5. Preserve exact `/api/*` behavior so no backend rewrite is needed.

## Step-by-Step Plan

### Task 1: Scaffold new layout shell in index.html

**Objective:** Replace the single-column feed+footer layout with a responsive top header, sidebar agent list, centered message feed, and bottom composer that stays usable on mobile.

**Files:** `C:\Users\Dad\Documents\HermesCoordination\index.html`

**Step 1:** Draft new shell in index.html:
- `<header>` with connection status + title/clock.
- `<div class="layout">` containing:
  - `<aside class="agents">` with agent list rendered from `/api/agents`
  - `<main class="feed">` for messages
  - `<footer class="composer">` fixed to bottom

**Step 2:** Add CSS:
- Desktop: `.layout { display: grid; grid-template-columns: 220px 1fr; gap: 12px; }`
- Mobile: collapse sidebar into top horizontal scrollable agent row; composer becomes compact row.
- Use existing color tokens; ensure same dark theme.

**Step 3:** Verify DOM by reading file only.

---

### Task 2: Agent sidebar with role chips and status

**Objective:** Make agents first-class in UI with name, role badge, and inferred online/offline state.

**Files:** `C:\Users\Dad\Documents\HermesCoordination\index.html`

**Step 1:** Add `.agents` CSS:
- Agent card: compact row showing avatar, name, role pill.
- States: green dot for just-seen messages, gray for idle.

**Step 2:** Update JS in `load()`:
- Render agent list into `.agents`.
- Clicking agent sets `t` (to) select to that agent.
- Update agent card styling when that agent appears in feed.

---

### Task 3: Composer rebuild

**Objective:** Make message creation faster and less error-prone.

**Files:** `C:\Users\Dad\Documents\HermesCoordination\index.html`

**Step 1:** Replace textarea heavy composer with:
- From/to chips auto-filled by agent list
- Type selector as segmented buttons: Chat, Assign, Status, Done, Yield, Inference
- Auto-expanding textarea with `Ctrl+Enter` / `Cmd+Enter` to send
- Visual validation: disable Send when content is empty

**Step 2:** Persist `from`, `to`, and `type` to `localStorage` so next visit remembers last sender/recipient.

---

### Task 4: Message feed improvements

**Objective:** Better readability and conversation threading.

**Files:** `C:\Users\Dad\Documents\HermesCoordination\index.html`

**Step 1:** Enhance `.msg` card:
- Group consecutive same-author messages with tighter spacing
- Improve timestamp display with relative time (`just now`, `5m`)
- Add copy button for message content

**Step 2:** Add simple filter row above feed:
- Show All / by type / by sender
- Filter uses client-side message array only

**Step 3:** Empty state:
- If `messages.length === 0`, show friendly onboarding instructions with example commands.

---

### Task 5: Mobile polish

**Objective:** Make the channel usable on phone screens.

**Files:** `C:\Users\Dad\Documents\HermesCoordination\index.html`

**Step 1:** Add responsive breakpoints:
- <= 640px: sidebar becomes horizontal scroll row at top, sticky
- Composer wraps textarea under type selector
- Larger tap targets for buttons and selectable agent chips

**Step 2:** Test via simulated narrow viewport or by inspecting CSS rules.

---

### Task 6: Accessibility and durability

**Objective:** Better keyboard navigation and focus behavior.

**Files:** `C:\Users\Dad\Documents\HermesCoordination\index.html`

**Step 1:** Add `aria-label` to selects/buttons already present; verify tab order is composer -> feed -> agents.
**Step 2:** Ensure status badges use semantic styling only; avoid relying on color alone.

---

### Task 7: Final validation

**Objective:** Confirm no API or behavior regressions.

**Files:** `C:\Users\Dad\Documents\HermesCoordination\index.html`, `C:\Users\Dad\Documents\HermesCoordination\relay.py`

**Step 1:** Start `relay.py` and POST a message using old format. Confirm it appears.
**Step 2:** Attempt `/api/agents` fetch and confirm JSON schema unchanged.

---

## Files Likely to Change

- `C:\Users\Dad\Documents\HermesCoordination\index.html`
- `C:\Users\Dad\Documents\HermesCoordination\channel.json` (only via existing UI)
- No backend rewrite planned.

## Tests / Validation

- Open desktop browser -> UI renders agents, feed, composer
- Send dummy chat message from each agent type -> JSON unchanged
- Resize browser to 320px -> layout remains usable
- Keyboard-only send with Ctrl+Enter -> works

## Risks, Tradeoffs, Open Questions

- Risk: larger HTML file from adding CSS inline; acceptable for local single-file app.
- Risk: adding JS may break on very old browsers; not required target.
- Open question: keep inline JS or extract `app.js`? Preference: keep inline for portability unless size demands split.
