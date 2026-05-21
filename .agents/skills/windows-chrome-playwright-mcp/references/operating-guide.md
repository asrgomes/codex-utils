# Windows Chrome Playwright MCP Operating Guide

Load this only after `SKILL.md` applicability passes.

## Hard Applicability Requirement

Use this skill only when the agent is running inside WSL2 on Windows and WSL can reach Windows
localhost through mirrored networking. Do not use it when the agent runs directly on native Windows,
macOS, a normal Linux desktop, a non-WSL container, or a remote browser service. Required
`%UserProfile%\.wslconfig` shape:

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

## Sandbox Escalation

Whenever running this skill's local scripts through Codex command execution, always request
permission escalation from the start. These scripts intentionally cross the WSL/Windows boundary and
may need `wslinfo`, host loopback networking, PowerShell, npm/npx, Chrome process inspection, or
debug-port probing that can fail inside the sandbox before the real connectivity check runs.

- Set `sandbox_permissions` to `require_escalated`.
- Use a short justification that names the Windows Chrome Playwright MCP connectivity or browser
  state check being performed.
- Suggest a narrow `prefix_rule` for the exact script family, such as `["node", "scripts/doctor.mjs"]`
  for doctor or preflight checks.
- If escalation is denied, stop and report that the skill cannot make a reliable connectivity
  decision from the sandboxed result.

This escalation is execution permission only. It does not replace the browser consent rules below.

## Browser Control Rule

Use Playwright MCP for normal browser operations, including opening URLs, tab selection, navigation,
clicking, typing, form filling, screenshots, downloads, uploads, and page inspection. Do not bypass
Playwright MCP with direct Chrome DevTools Protocol calls such as `/json/new`, `/json/list`, or raw
WebSocket commands for ordinary browsing tasks.

Direct Chrome/CDP checks are allowed only for connectivity, ownership, and health decisions inside
the skill scripts, such as verifying `/json/version`, checking whether the skill-owned Chrome profile
is running, or diagnosing why Playwright MCP cannot attach. If the configured `windows-chrome` MCP
tools are unavailable in the current Codex session, run setup or troubleshooting and report the
session limitation instead of performing the requested browser operation through direct CDP.

When this skill is active, do not load or use the separate `alm-browser-playwright` skill for the
same task. For Oracle ALM / Visual Builder Studio pages, keep the interaction in this skill's
Playwright MCP flow unless the user explicitly asks to switch skills.

## Activation And Consent

Use this skill automatically when direct browser control is clearly needed and ordinary HTTP
retrieval or APIs are not enough. Browser control is justified for authenticated browser state,
clicking, typing, dialogs, forms, JavaScript-rendered UI, visual checks, screenshots, downloads,
uploads, SSO/2FA/bot checks, or reproducing what a human sees in Windows Chrome.

If the user explicitly loads or names this skill without a concrete browser action, treat that as
approval to use it. Immediately run preflight checks only, using the permission escalation rule
above:

```bash
node scripts/doctor.mjs --preflight
```

Then wait for instructions that require browser interaction. If the same user request already
contains a concrete browser action, do not run a separate preflight first; use the `windows-chrome`
MCP server and let `scripts/playwright-mcp-wrapper.mjs` run the readiness checks when the first
browser tool is called. Do not ask again before using Chrome for those browser-interaction
instructions. Do not start or reuse Chrome during Codex startup, MCP initialization, or tool
discovery; wait until an actual browser interaction is needed.

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
the Codex MCP server named `windows-chrome`. The registration script verifies the current
`windows-chrome` command and replaces stale or disabled entries. Scripts require Node.js 24+ and use
modern built-in Node APIs. Playwright MCP is installed into this skill's local `.runtime/` directory,
which is ignored by git. If Codex does not expose newly registered MCP tools in the current session,
tell the user to restart the Codex CLI session after setup.

## Browser Workflow

When browser control is approved:

1. Use the configured `windows-chrome` MCP server. Its command is `node scripts/playwright-mcp-wrapper.mjs`.
2. Perform page operations through Playwright MCP, even simple URL opens.
3. Do not run an extra manual preflight immediately before starting the MCP server; the wrapper is
   the browser-action readiness gate.
4. MCP startup and `tools/list` are side-effect-free with respect to Windows Chrome.
5. On the first browser tool call, the wrapper fails fast if WSL2 mirrored networking, PowerShell,
   Windows Chrome, Node.js 24+, npm, npx, or port ownership checks fail.
6. On that same first browser tool call, the wrapper starts the dedicated Windows Chrome debug
   profile only if it is not already healthy, then waits for
   `http://localhost:${WINDOWS_CHROME_CDP_PORT:-9223}/json/version`.
7. The wrapper runs Playwright MCP in-process and connects it to Chrome lazily, equivalent to:

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

Run these commands with the permission escalation rule above:

```bash
node scripts/doctor.mjs
node scripts/ensure-playwright-mcp.mjs
node scripts/status.mjs
node scripts/stop-chrome-debug.mjs
node scripts/install-codex-mcp.mjs
```

Load `references/browser-interaction-idioms.md` before operating on pages. Load
`references/troubleshooting.md` when a script fails or the MCP server does not appear in Codex.
