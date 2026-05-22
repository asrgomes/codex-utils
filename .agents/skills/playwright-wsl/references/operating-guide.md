# Playwright WSL Operating Guide

Load this only after `SKILL.md` applicability passes.

## Hard Applicability Requirement

Use this skill only when the agent is running inside WSL2 on Windows and WSL can reach Windows
localhost through mirrored networking. Do not use it from native Windows, macOS, normal Linux,
containers, or remote browser services.

Required `%UserProfile%\.wslconfig` shape:

```ini
[wsl2]
networkingMode=mirrored
dnsTunneling=true

[experimental]
hostAddressLoopback=true
```

If `wslinfo --networking-mode` is unavailable, does not print `mirrored`, or WSL cannot reach the
Chrome DevTools endpoint after the skill starts Chrome, stop and report the observed output. Do not
try NAT workarounds, `0.0.0.0` Chrome debugging, port proxies, or a Windows-native fallback.

## Sandbox Escalation

Always request permission escalation when running this skill's scripts through Codex command
execution. The scripts cross the WSL/Windows boundary and may need `wslinfo`, host loopback
networking, PowerShell, npm package installation, Chrome process inspection, or debug-port probing.

- Set `sandbox_permissions` to `require_escalated`.
- Use a justification naming Playwright WSL setup or browser state.
- Suggest a narrow `prefix_rule`, such as `["node", "scripts/playwright-cli.mjs"]` for browser
  actions or `["node", "scripts/doctor.mjs"]` for preflight.
- If escalation is denied, stop and report that the sandboxed result is not reliable.

## Browser Control Rule

Use a persistent Playwright CLI session through `node scripts/playwright-cli.mjs ...` for page
operations. Do not register or call any separate long-running browser server for this skill. The
runner manages the session bootstrap:

1. `doctor.mjs --preflight` verifies WSL2, mirrored networking, PowerShell, Windows Chrome, and
   automatically installs local Playwright CLI dependencies if missing.
2. `chrome-debug.mjs ensure` starts or reuses only the predefined skill Chrome profile.
3. The runner checks the named Playwright CLI session and attaches it to Chrome only when it is not
   already open.
4. After a successful command, the runner records a short-lived warm-start cache in `.runtime/`.
5. Later `node scripts/playwright-cli.mjs ...` invocations reuse that same session. When the cache is
   fresh and Chrome CDP plus the Playwright CLI session are healthy, the runner skips the slower
   PowerShell setup checks for that command.

Do not detach or stop Chrome between ordinary page operations. Keep issuing commands with the same
session until the browser task is complete.

The predefined Chrome profile is:

```text
%LOCALAPPDATA%\Codex\playwright-wsl\profile
```

`WINDOWS_CHROME_PROFILE_PATH` may override this only for deliberate troubleshooting.

Set `PLAYWRIGHT_WSL_FAST_START=0` to disable the warm-start cache and force the full preflight plus
Chrome ownership checks on every browser command.

## Activation And Consent

Use this skill automatically when direct browser control is clearly needed and ordinary HTTP
retrieval or APIs are not enough. Browser control is justified for authenticated browser state,
clicking, typing, dialogs, forms, JavaScript-rendered UI, visual checks, screenshots, downloads,
uploads, SSO/2FA/bot checks, or reproducing what a human sees in Windows Chrome.

If the user explicitly loads or names this skill without a concrete browser action, run only:

```bash
node scripts/doctor.mjs --preflight
```

Then wait for browser instructions. If the same user request already contains a concrete browser
action, run `node scripts/playwright-cli.mjs <command>` directly; the runner performs preflight
first. Do not ask again for Chrome usage when the user already requested browser interaction.

Do not infer browser consent from a generic task. If browser intent is unclear, ask before opening
Windows Chrome.

## Setup

Manual setup is optional because preflight installs Playwright CLI automatically. To validate the
environment up front, run:

```bash
node scripts/bootstrap.mjs
```

## Browser Workflow

Run commands from this skill directory:

```bash
node scripts/playwright-cli.mjs open https://example.com
node scripts/playwright-cli.mjs snapshot
node scripts/playwright-cli.mjs click e3
node scripts/playwright-cli.mjs type "search text"
node scripts/playwright-cli.mjs screenshot --filename=page.png
```

`open <url>` is accepted as a convenience and maps to `goto <url>` in the persistent session. Raw
`attach` is reserved for the runner. Explicit lifecycle commands such as `detach`, `close`,
`kill-all`, and `delete-data` pass through to Playwright CLI and should be used only when cleanup or
session reset is intentional.

After finishing the browser task, detach the Playwright CLI session if needed:

```bash
node scripts/playwright-cli.mjs detach
```

Stop the predefined Windows Chrome profile only when you are done with browser work:

```bash
node scripts/stop-chrome-debug.mjs
```

Load `references/browser-interaction-idioms.md` before operating on pages. Load
`references/troubleshooting.md` when a script fails.
