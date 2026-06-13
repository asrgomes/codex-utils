---
name: markdown-format
description: >
  Use when creating, editing, reviewing, linting, validating, or checking Markdown files or Markdown
  content for syntax, formatting, structure, wrapping, line-length enforcement, prettier,
  markdownlint, README syntax review, README cleanup, or automatically installing missing Markdown
  formatting tools.
---

# Markdown Formatting

## Overview

Format Markdown in two steps: `prettier` first, `markdownlint` second. Use project-local config when
it exists. If required tools are missing, install them automatically before formatting unless the
user explicitly forbids installation.

## When to Use

- Creating or editing `*.md` files
- Reviewing Markdown syntax or formatting
- Reviewing Markdown structure or README syntax
- Checking Markdown content before sharing or committing
- Linting or validating Markdown formatting
- Cleaning up `README` or docs formatting
- Enforcing wrapping or 100-column prose width
- Running `prettier` and `markdownlint` consistently
- Automatically installing missing Markdown tooling before formatting

Do not use this skill for non-Markdown files.

## Required Tools

- `prettier`
- `markdownlint` from `markdownlint-cli`

## Workflow

1. Check tools before editing:

   ```bash
   npx --no-install prettier --version
   npx --no-install markdownlint --version
   ```

2. If either command fails, install the required tools automatically.
   - If the target project has `package.json`, install project-local dev dependencies:

     ```bash
     npm install -D prettier markdownlint-cli
     ```

   - If the target project has no `package.json`, install global tools:

     ```bash
     npm install -g prettier markdownlint-cli
     ```

   - If `npm` is unavailable, tell the user to install Node.js LTS first and report that formatting
     did not run.
   - If the environment requires approval for network or global installation, request approval and
     continue after it is granted.
   - Do not stop at a missing-tool report before attempting installation, unless the user explicitly
     said not to install tools.

3. Verify the tools after any install:

   ```bash
   npx --no-install prettier --version
   npx --no-install markdownlint --version
   ```

4. Look for project config before using fallback flags:
   - Prettier: `.prettierrc*`, `prettier.config.*`, `package.json` with `prettier`
   - Markdownlint: `.markdownlint.*`, `.markdownlint-cli2.*`
5. Run `prettier` first.
   - With project config:

     ```bash
     npx prettier --write path/to/file.md
     ```

   - Without project config:

     ```bash
     npx prettier --write --print-width 100 --prose-wrap always path/to/file.md
     ```

6. Run `markdownlint` second.
   - With project config:

     ```bash
     npx markdownlint path/to/file.md --fix
     ```

   - Without project config:

     ```bash
     npx markdownlint path/to/file.md --fix --config <(cat <<'JSON'
     {
       "MD013": { "line_length": 100 }
     }
     JSON
     )
     ```

7. Re-read the file if needed and confirm prose is wrapped and no prose line exceeds 100 characters
   unless project config says otherwise.

## Defaults

Use these only when project config is missing:

- `prettier --print-width 100 --prose-wrap always`
- `markdownlint` rule `MD013.line_length = 100`

## Auto-Install Rules

- Auto-install missing `prettier` and `markdownlint-cli` before formatting.
- Prefer `npm install -D prettier markdownlint-cli` when the target project has `package.json`.
- Use `npm install -g prettier markdownlint-cli` only when there is no project package file.
- Verify both tools after installation.
- If installation fails, report the failed command, the error, and that formatting did not run.
- Respect an explicit user instruction not to install tools.

Install commands:

```bash
npm install -D prettier markdownlint-cli
npm install -g prettier markdownlint-cli
```

Verify commands:

```bash
npx --no-install prettier --version
npx --no-install markdownlint --version
```

## Common Mistakes

- Running `markdownlint` before `prettier` and creating noisy follow-up diffs
- Applying fallback flags when the repo already has local config
- Claiming formatting succeeded when install or verification failed
- Returning a missing-tool report before attempting the required auto-install
- Formatting non-Markdown files with this workflow

## Quick Check

- Project config was used when present
- `prettier` ran before `markdownlint`
- Prose is wrapped
- Prose lines are at or under 100 characters when fallback defaults apply
