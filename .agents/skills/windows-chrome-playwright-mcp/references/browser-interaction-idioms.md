# Browser Interaction Idioms

Use Playwright MCP through the configured `windows-chrome` server. Tool names vary by client, but
the preferred pattern is stable.

## Page Navigation

1. Navigate directly to the target URL.
2. Wait for the page to settle.
3. Inspect the accessibility snapshot before acting.
4. Prefer semantic targets over coordinates.

Good targets:

- role and accessible name: button "Sign in"
- label: textbox labeled "Email"
- placeholder: input placeholder "Search"
- visible link text

Avoid coordinate clicks unless the page has no accessible or DOM-stable target and the user needs a
visual-only interaction.

## Forms And Actions

- Fill fields by label, placeholder, or role.
- Click buttons and links by role/name.
- After each submit/navigation, wait for an observable page state: URL change, heading, status text,
  dialog, table row, download event, or error message.
- For multi-step flows, summarize the current page before the next destructive or irreversible
  action.

## Authentication

The Chrome profile is persistent. If login, SSO, 2FA, CAPTCHA, or a hardware prompt blocks progress,
pause and ask the user to complete it in the Windows Chrome window. Resume after the user confirms.

Do not extract secrets from the page. Do not paste credentials unless the user explicitly provides
them for this session.

## Visual Checks

Use screenshots when visual state matters: layout, canvas, charts, generated images, PDF previews,
drag/drop state, or pixel-level rendering. Otherwise prefer accessibility snapshots because they are
more stable and cheaper to reason over.

## Downloads And Uploads

For downloads, wait for the browser download event and report the saved path. For uploads, use a
user-provided local path and confirm that the file exists before submitting.

## Unsafe Page Scripting

Avoid direct page JavaScript evaluation unless ordinary MCP actions cannot express the task. If
script evaluation is needed, state why and avoid reading secrets or mutating unrelated page state.
