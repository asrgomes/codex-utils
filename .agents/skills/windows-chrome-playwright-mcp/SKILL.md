---
name: windows-chrome-playwright-mcp
description: Use when an agent running in WSL2 on Windows 11 needs direct Windows Chrome control through Playwright MCP because HTTP requests or APIs are insufficient for login state, interactive UI, JavaScript-rendered pages, screenshots, downloads, uploads, or forms; requires WSL2 mirrored networking with host loopback.
---

# Windows Chrome Playwright MCP

## Purpose

Control a dedicated persistent Windows Chrome profile from a WSL2 Codex agent through Playwright MCP.
Use this only after browser control is justified and the WSL2 mirrored-networking contract passes.

## Hard Applicability Requirement

Use this skill only when the agent is running inside WSL2 on Windows 11 and WSL can reach Windows
localhost through mirrored networking. Required `%UserProfile%\.wslconfig` shape:

```ini
[wsl2]
networkingMode=mirrored
dnsTunneling=true

[experimental]
hostAddressLoopback=true
```

Recommended where appropriate:

```ini
[wsl2]
firewall=false
autoProxy=true
```

If `wslinfo --networking-mode` is unavailable, does not print `mirrored`, or WSL cannot reach the
Chrome DevTools endpoint after the skill starts Chrome, stop. Report the observed output and the
required `.wslconfig` settings. Do not try NAT workarounds, `0.0.0.0` Chrome debugging, port proxies,
or a Windows-native Playwright MCP fallback.

## Activation And Consent

Use this skill automatically when direct browser control is clearly needed and ordinary HTTP
retrieval or APIs are not enough. Browser control is justified for authenticated browser state,
clicking, typing, dialogs, forms, JavaScript-rendered UI, visual checks, screenshots, downloads,
uploads, SSO/2FA/bot checks, or reproducing what a human sees in Windows Chrome.

If the user explicitly loads or names this skill, treat that as approval to use it. Immediately run
preflight checks only:

```bash
node scripts/doctor.mjs --preflight
```

Then wait for instructions that require browser interaction. Do not ask again before using Chrome
for those browser-interaction instructions. Do not start or reuse Chrome until an actual browser
interaction is needed.

Do not infer browser consent from a generic task. If the user did not explicitly mention browser,
Chrome, opening a site, clicking, screenshots, visual inspection, downloads/uploads, or equivalent
intent, ask first:

> This may require controlling Windows Chrome rather than using direct HTTP requests. Can I open
> Chrome in Windows to complete it?

Only start or reuse Chrome after explicit skill invocation, explicit browser intent, or user
approval.

## One-Time Setup

From this skill directory, run:

```bash
node scripts/bootstrap.mjs
```

This verifies WSL2 mirrored networking, checks required tools, primes `@playwright/mcp`, and registers
the Codex MCP server named `windows-chrome`. Scripts require Node.js 24+ and use modern built-in
Node APIs. Playwright MCP is installed into this skill's local `.runtime/` directory, which is
ignored by git. If Codex does not expose newly registered MCP tools in the current session, tell the
user to restart the Codex CLI session after setup.

## Browser Workflow

When browser control is approved:

1. Use the configured `windows-chrome` MCP server. Its command is `node scripts/playwright-mcp-wrapper.mjs`.
2. The wrapper fails fast if WSL2 mirrored networking, PowerShell, Windows Chrome, Node.js 24+,
   npm, npx, or port ownership checks fail.
3. The wrapper starts the dedicated Windows Chrome debug profile only if it is not already healthy.
4. The wrapper waits for `http://localhost:${WINDOWS_CHROME_CDP_PORT:-9223}/json/version`.
5. The wrapper `exec`s Playwright MCP in the foreground:

```bash
skills/windows-chrome-playwright-mcp/.runtime/node_modules/.bin/playwright-mcp \
  --cdp-endpoint=http://localhost:9223
```

The Chrome profile is separate from the user's normal browser profile and persists across Codex
sessions:

```text
%LOCALAPPDATA%\Codex\windows-chrome-playwright-mcp\profile
```

## Safety Rules

- Attach only to Chrome debug processes using this skill's expected profile path.
- If port `9223` is occupied by anything else, stop and report it.
- Never kill the user's normal Chrome. Cleanup scripts may stop only skill-owned Chrome processes.
- Keep Playwright MCP in the foreground on stdio. Do not detach it with `nohup`, `Start-Process`, or
  background shell operators.
- Leave the dedicated Chrome profile running after normal MCP shutdown unless the user asks to stop it.

## Common Commands

```bash
node scripts/doctor.mjs
node scripts/ensure-playwright-mcp.mjs
node scripts/status.mjs
node scripts/stop-chrome-debug.mjs
node scripts/install-codex-mcp.mjs
```

Load `references/browser-interaction-idioms.md` before operating on pages. Load
`references/troubleshooting.md` when a script fails or the MCP server does not appear in Codex.
