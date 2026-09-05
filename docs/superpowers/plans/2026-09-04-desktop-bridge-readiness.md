# Desktop Bridge HTTP Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the React Desktop 2.0 chat UI show a ready Bridge when its local HTTP status endpoint confirms `{ ok: true, ready: true }`, even if the optional WebSocket event channel cannot open.

**Architecture:** The public React source checkout at `C:\Users\11208\AppData\Local\Temp\genericagent-react-source-20260904` is the source of truth. `src/services/ws.ts` will probe `GET /status` alongside the existing WebSocket connection; the status endpoint controls UI readiness while the WebSocket remains responsible for event delivery and retries. After an explicit authorization gate for publishing the local source commit, import only the rebuilt renderer assets and provenance into the compiled-only repository.

**Tech Stack:** React 18, TypeScript, Vitest 4, Vite 6, Tauri generated assets, Node.js.

---

## File Structure

- `C:\Users\11208\AppData\Local\Temp\genericagent-react-source-20260904\frontends\desktop\src\services\ws.ts`: renderer Bridge state and WebSocket subscription lifecycle.
- `C:\Users\11208\AppData\Local\Temp\genericagent-react-source-20260904\frontends\desktop\src\__tests__\bridge\http-readiness.test.ts`: regression test for an HTTP-ready Bridge whose WebSocket closes.
- `D:\navy_code\github_code\GenericAgent\frontends\desktop\dist\**`: generated React renderer assets imported after upstream publication.
- `D:\navy_code\github_code\GenericAgent\frontends\desktop\scripts\verify-compiled-dist.mjs`: validates published source SHA and the final distribution manifest.
- `D:\navy_code\github_code\GenericAgent\frontends\desktop\dist\README.md`: generated distribution provenance naming the published source commit.
- `D:\navy_code\github_code\GenericAgent\frontends\desktop\dist\build-provenance.json`: source commit, generated asset count, and manifest SHA-256.

### Task 1: Correct the Readiness Contract

**Files:**
- Modify: `D:\navy_code\github_code\GenericAgent\docs\superpowers\specs\2026-09-04-desktop-bridge-readiness-design.md`

- [ ] **Step 1: State the actual UI readiness condition**

Replace the WebSocket prerequisite with the affirmative HTTP payload `{ ok: true, ready: true }`. State that the WebSocket remains an event-delivery channel and that its closure does not supersede an HTTP-confirmed ready state.

- [ ] **Step 2: State the regression and manual checks**

Require a regression case where `/status` succeeds and the WebSocket fails before opening, and require the desktop chat page to leave `连接中` whenever that `/status` response is healthy.

- [ ] **Step 3: Review the document**

Run: `rg -n "WebSocket|HTTP|connecting|ready" docs/superpowers/specs/2026-09-04-desktop-bridge-readiness-design.md`

Expected: HTTP readiness is sufficient and an open WebSocket is not a prerequisite for the ready UI state.

- [ ] **Step 4: Commit the documentation correction**

Run:

```powershell
git add docs/superpowers/specs/2026-09-04-desktop-bridge-readiness-design.md
git commit -m "docs: clarify desktop bridge readiness"
```

Expected: one commit containing only the readiness-design correction.

### Task 2: Write and Prove the Failing Source Regression Test

**Files:**
- Create: `C:\Users\11208\AppData\Local\Temp\genericagent-react-source-20260904\frontends\desktop\src\__tests__\bridge\http-readiness.test.ts`

- [ ] **Step 1: Add a WebSocket fake that closes before opening and a healthy HTTP status mock**

```ts
// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

class ClosingWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 3;
  readonly readyState = ClosingWebSocket.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(_url: string) {
    queueMicrotask(() => this.onclose?.());
  }

  close() {
    this.onclose?.();
  }
}

describe('Bridge HTTP readiness', () => {
  beforeEach(() => {
    vi.stubGlobal('WebSocket', ClosingWebSocket);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, ready: true }),
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllTimers();
  });

  it('becomes ready when status is healthy even if the event socket closes', async () => {
    vi.resetModules();
    const { getBridgeStatus, subscribe } = await import('../../services/ws');
    const unsubscribe = subscribe('bridge-ready', () => {});

    await vi.waitFor(() => expect(getBridgeStatus()).toBe('ready'));
    expect(fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:14168/status',
      { cache: 'no-store' },
    );
    unsubscribe();
  });
});
```

- [ ] **Step 2: Run the new test before the fix**

Run: `npm run test:bridge -- http-readiness.test.ts`

Working directory: `C:\Users\11208\AppData\Local\Temp\genericagent-react-source-20260904\frontends\desktop`

Expected: FAIL because the pre-fix `ws.ts` does not issue a status request and leaves the state at `connecting` when the fake socket closes.

### Task 3: Implement Source HTTP Readiness

**Files:**
- Modify: `C:\Users\11208\AppData\Local\Temp\genericagent-react-source-20260904\frontends\desktop\src\services\ws.ts`

- [ ] **Step 1: Import the HTTP Bridge base URL and create a deduplicated probe**

```ts
import { BRIDGE_BASE, WS_URL } from './constants';

let readinessProbe: Promise<boolean> | null = null;

function probeReadiness(): Promise<boolean> {
  if (readinessProbe) return readinessProbe;
  readinessProbe = fetch(`${BRIDGE_BASE}/status`, { cache: 'no-store' })
    .then(async (response) => {
      if (!response.ok) return false;
      const status = await response.json() as { ok?: unknown; ready?: unknown };
      const isReady = status.ok === true && status.ready === true;
      if (isReady) setStatus('ready');
      return isReady;
    })
    .catch(() => false)
    .finally(() => { readinessProbe = null; });
  return readinessProbe;
}
```

- [ ] **Step 2: Run the probe with every socket connection attempt**

Immediately after `setStatus('connecting');` in `connect()`, add `void probeReadiness();`. Retain `new WebSocket(WS_URL)` and the existing `ws.onopen` handler so event delivery continues to reset reconnect backoff.

- [ ] **Step 3: Probe instead of unconditionally downgrading on socket close**

In `ws.onclose`, replace `setStatus('connecting');` with the following state settlement, then leave `scheduleReconnect();` unchanged:

```ts
void probeReadiness().then((isReady) => {
  if (!isReady) setStatus('connecting');
});
```

A successful probe therefore retains or restores ready. A failed probe moves the closed event channel back to connecting, so a Bridge that has actually gone offline cannot remain ready indefinitely.

- [ ] **Step 4: Run the focused test after the fix**

Run: `npm run test:bridge -- http-readiness.test.ts`

Working directory: `C:\Users\11208\AppData\Local\Temp\genericagent-react-source-20260904\frontends\desktop`

Expected: PASS; the state reaches ready and the request is exactly `fetch('http://127.0.0.1:14168/status', { cache: 'no-store' })`.

- [ ] **Step 5: Run source verification**

Run: `npm run test:bridge`

Working directory: `C:\Users\11208\AppData\Local\Temp\genericagent-react-source-20260904\frontends\desktop`

Expected: PASS.

Run: `npm run typecheck`

Working directory: `C:\Users\11208\AppData\Local\Temp\genericagent-react-source-20260904\frontends\desktop`

Expected: PASS with no TypeScript diagnostics.

- [ ] **Step 6: Commit the source change locally**

Run:

```powershell
git add frontends/desktop/src/services/ws.ts frontends/desktop/src/__tests__/bridge/http-readiness.test.ts
git commit -m "fix(desktop): use bridge HTTP readiness"
```

Working directory: `C:\Users\11208\AppData\Local\Temp\genericagent-react-source-20260904`

Expected: a local source commit containing only the new regression test and the readiness implementation.

### Task 4: Publish Source After Explicit User Authorization

**Files:**
- Modify: none before authorization.

- [ ] **Step 1: Stop after the local source commit and request publication authority**

Report the local source SHA and successful tests. Ask for approval before pushing or creating a pull request because the generated renderer README requires source contributions to be published to `https://github.com/abraxas914/GenericAgent` before a compiled distribution is imported.

- [ ] **Step 2: Push only after approval**

Run: `git push origin HEAD:codex/desktop-http-readiness`

Working directory: `C:\Users\11208\AppData\Local\Temp\genericagent-react-source-20260904`

Expected: a remote `codex/desktop-http-readiness` branch whose tip matches `git rev-parse HEAD`.

### Task 5: Build and Import the Published Renderer

**Files:**
- Modify: `D:\navy_code\github_code\GenericAgent\frontends\desktop\dist\**`
- Modify: `D:\navy_code\github_code\GenericAgent\frontends\desktop\scripts\verify-compiled-dist.mjs`

- [ ] **Step 1: Build and validate the source distribution**

Run: `npm run build`

Working directory: `C:\Users\11208\AppData\Local\Temp\genericagent-react-source-20260904\frontends\desktop`

Expected: Vite writes the updated renderer assets to `dist` without errors.

Run: `npm run test:bundle`

Working directory: `C:\Users\11208\AppData\Local\Temp\genericagent-react-source-20260904\frontends\desktop`

Expected: the source checkout's asset-integrity test passes.

- [ ] **Step 2: Replace only compiled renderer files**

Compare the source and destination `dist` file lists, then replace `D:\navy_code\github_code\GenericAgent\frontends\desktop\dist` with the source checkout's generated `dist`. Preserve the generated README and provenance metadata expected by this repository, and do not copy `src`, `public`, `e2e`, Vite configuration, `package-lock.json`, or `node_modules`.

- [ ] **Step 3: Recompute generated provenance from the final destination files**

Use the published `git rev-parse HEAD` source SHA in `dist/README.md` and `dist/build-provenance.json`. Exclude `README.md` and `build-provenance.json` from the manifest; sort final relative POSIX paths with `localeCompare('en')`; hash each line as the file's SHA-256, two spaces, its relative path, and a newline; then hash the concatenated manifest. Write the exact resulting asset count and manifest SHA to `build-provenance.json`.

- [ ] **Step 4: Point the compiled verifier at the published source commit**

Replace only the `expectedSourceCommit` constant in `frontends/desktop/scripts/verify-compiled-dist.mjs` with the source SHA published in Task 4. Do not alter the version, license checks, renderer boundary checks, or manifest validation logic.

- [ ] **Step 5: Validate the compiled-only repository**

Run: `npm run test:dist`

Working directory: `D:\navy_code\github_code\GenericAgent\frontends\desktop`

Expected: `Compiled React Desktop 2.0 distribution contracts passed.`

Run: `rg -l "127.0.0.1:14168/status" frontends/desktop/dist/assets`

Working directory: `D:\navy_code\github_code\GenericAgent`

Expected: at least one generated JavaScript asset is listed.

- [ ] **Step 6: Commit the renderer refresh**

Run:

```powershell
git add frontends/desktop/dist frontends/desktop/scripts/verify-compiled-dist.mjs
git commit -m "fix(desktop): refresh bridge readiness renderer"
```

Expected: generated distribution assets and one verifier provenance-SHA update, with no React development source files.

### Task 6: Verify the Original Desktop Workflow

**Files:**
- Modify: none.

- [ ] **Step 1: Restart the desktop development launcher**

Run: `.\launch_desktop_dev.cmd`

Working directory: `D:\navy_code\github_code\GenericAgent`

Expected: the launcher starts healthy Bridge and Conductor services and opens the Tauri desktop window.

- [ ] **Step 2: Inspect the chat UI with a healthy status endpoint**

With `http://127.0.0.1:14168/status` returning `{ "ok": true, "ready": true }`, inspect the main chat view.

Expected: the input is enabled and the page no longer shows `连接中`; an unavailable WebSocket alone does not return it to that state.

- [ ] **Step 3: Record the final state**

Run: `git status --short --branch`

Working directory: `D:\navy_code\github_code\GenericAgent`

Expected: planned commits plus the pre-existing untracked user files only.
