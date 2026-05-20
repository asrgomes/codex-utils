# Troubleshooting

## Skill Does Not Apply

If the agent is not running in WSL2 on Windows 11 with mirrored networking, stop and report:

```text
This skill only supports agents running inside WSL2 with mirrored networking enabled.

Required %UserProfile%\.wslconfig:
  [wsl2]
  networkingMode=mirrored
  dnsTunneling=true

  [experimental]
  hostAddressLoopback=true

Observed:
  <command output>

No browser automation was attempted.
```

## MCP Tools Do Not Appear

Run:

```bash
node scripts/ensure-playwright-mcp.mjs
node scripts/install-codex-mcp.mjs
codex mcp get windows-chrome
```

If the server was just added, restart the Codex CLI session. Some clients load MCP server
configuration only at session start.

## Playwright MCP Install Fails

The skill installs `@playwright/mcp` into `.runtime/` under the skill directory. If install fails,
confirm Node.js 24+ is active and check npm proxy and registry access from WSL:

```bash
node -v
npm config get registry
npm ping
node scripts/ensure-playwright-mcp.mjs
```

## Chrome Does Not Start

Run:

```bash
node scripts/doctor.mjs --preflight
node scripts/ensure-windows-chrome-debug.mjs
node scripts/status.mjs
```

If Chrome is not installed, install Google Chrome on Windows or add `chrome.exe` to Windows PATH.

## Port Is Occupied

The skill refuses to attach to unknown processes on the selected CDP port. Either stop the other
process or choose a different port:

```bash
export WINDOWS_CHROME_CDP_PORT=9224
node scripts/install-codex-mcp.mjs
```

Use one port consistently for a Codex session.

## Stop The Dedicated Chrome Profile

This stops only Chrome processes whose command line contains the skill profile path:

```bash
node scripts/stop-chrome-debug.mjs
```

It must not stop the user's normal Chrome profile.
