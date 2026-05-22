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

## Playwright CLI Install Fails

Preflight runs `node scripts/ensure-playwright-cli.mjs` automatically. If it fails, confirm Node.js
24+ is active and check npm proxy and registry access from WSL:

```bash
node -v
npm config get registry
npm ping
node scripts/doctor.mjs --preflight
```

The skill must fail if Playwright CLI cannot be installed.

## Chrome Does Not Start

Run with permission escalation:

```bash
node scripts/doctor.mjs --preflight
node scripts/ensure-windows-chrome-debug.mjs
node scripts/status.mjs
```

If Chrome is not installed, install Google Chrome on Windows or add `chrome.exe` to Windows PATH.

## Port Is Occupied

The skill refuses to attach to unknown processes on the selected CDP port. Either stop the other
process or choose a different port consistently for the command:

```bash
export WINDOWS_CHROME_CDP_PORT=9224
node scripts/playwright-cli.mjs open https://example.com
```

## Stop The Predefined Chrome Profile

The runner keeps Chrome open across ordinary page operations. To clean up manually after browser
work is complete:

```bash
node scripts/playwright-cli.mjs detach
node scripts/stop-chrome-debug.mjs
```

This stops only Chrome processes whose command line contains the predefined skill profile path. It
must not stop the user's normal Chrome profile.
