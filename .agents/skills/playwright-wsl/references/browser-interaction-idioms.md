# Browser Interaction Idioms

Use the same persistent Playwright CLI session through `node scripts/playwright-cli.mjs`. Do not
call raw CDP endpoints for page operations.

## Page Navigation

1. Navigate with `open <url>` or `goto <url>`.
2. Capture `snapshot` before acting.
3. Use element refs from the snapshot for clicks, fills, uploads, and screenshots.
4. Prefer semantic targets and refs over coordinates.

Useful commands:

```bash
node scripts/playwright-cli.mjs open https://example.com
node scripts/playwright-cli.mjs snapshot
node scripts/playwright-cli.mjs click e3
node scripts/playwright-cli.mjs fill e5 "user@example.com" --submit
node scripts/playwright-cli.mjs screenshot --filename=page.png
```

## Forms And Actions

- Fill fields by label, placeholder, role, or snapshot ref.
- After each submit/navigation, wait for an observable page state: URL change, heading, status text,
  dialog, table row, download event, or error message.
- For multi-step flows, summarize the current page before the next destructive or irreversible
  action.

## Authentication

The Chrome profile and Playwright CLI session persist across commands. If login, SSO, 2FA, CAPTCHA,
or a hardware prompt blocks progress, ask the user to complete it in the Windows Chrome window, then
continue with the next `node scripts/playwright-cli.mjs ...` command.

Do not extract secrets from the page. Do not paste credentials unless the user explicitly provides
them for this session.

## Visual Checks

Use screenshots when visual state matters: layout, canvas, charts, generated images, PDF previews,
drag/drop state, or pixel-level rendering. Otherwise prefer snapshots because they are more stable
and cheaper to reason over.

## Downloads And Uploads

For downloads, use Playwright CLI support and report the saved path. For uploads, use a
user-provided local path and confirm the file exists before submitting.

## Unsafe Page Scripting

Avoid `run-code` or direct page JavaScript unless ordinary CLI commands cannot express the task. If
script evaluation is needed, state why and avoid reading secrets or mutating unrelated page state.
