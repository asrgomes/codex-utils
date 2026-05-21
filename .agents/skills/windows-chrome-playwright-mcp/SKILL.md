---
name: windows-chrome-playwright-mcp
description: Use only when an agent is running inside WSL2 on Windows and needs direct Windows Chrome control through Playwright MCP for authenticated or interactive browser work. Do not use for native Windows, macOS, Linux desktop, containers, or remote browser services.
---

# Windows Chrome Playwright MCP

## Applicability Gate

Use this skill only if all are true:

- The agent is running inside WSL2 on Windows.
- The task needs direct Windows Chrome control through Playwright MCP.
- HTTP/API access is insufficient because the task needs authenticated browser state, interactive
  UI, JavaScript-rendered state, screenshots, downloads/uploads, forms, SSO, or what a human sees.

Do not use this skill for native Windows, macOS, Linux desktop, non-WSL containers, or remote browser
services. If the gate fails, stop and say the skill does not apply.

If the gate passes, load `references/operating-guide.md` before setup, browser use, or troubleshooting.
