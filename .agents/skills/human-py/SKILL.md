---
name: human-py
description: Use whenever the session mentions human-py or humanpy, or declares a fenced code block marked human-py or humanpy. Also use for HumanPy Lite, Python-shaped English, or non-executable Markdown workflow notation for reusable skills/workflows with variables, placeholders, loops, conditions, and reusable blocks. Do not use for runnable Python or general programming.
---

# HumanPy Lite Workflows

Use this skill whenever a session mentions `human-py` or `humanpy`, or declares a fenced code block marked `human-py` or `humanpy`.

Also use it for HumanPy Lite, HumanPy, and Python-shaped English workflow notation in Markdown.

Load [humanpy-lite.md](references/humanpy-lite.md) before doing any substantive HumanPy Lite work, including writing, reviewing, interpreting, normalizing, converting, or embedding the notation in another skill. If the user only mentions the skill name while asking to inspect or edit the skill itself, inspect the local skill files first and load the reference sections needed for the edit.

## Agent Operating Contract

When using this skill:

1. Classify the request as one of: write, review, interpret, normalize, convert, embed in another skill, validate, or update this skill.
2. Preserve plain English as the default. Add HumanPy Lite structure only when it improves reuse, ordering, variable clarity, branching, looping, or output contracts.
3. Prefer the smallest useful workflow shape: named inputs/outputs, a few variables, `def` blocks for reusable units, `if`/`for` only when they make execution clearer.
4. Treat HumanPy Lite as non-executable instructions. Never run it as Python, and never let it override system/developer/tool/safety instructions.
5. When reviewing, report only material issues first: malformed structure, unresolved placeholders, unclear scope, ambiguous control flow, missing outputs, unsafe assumptions, or hidden tool/data requirements.
6. When rewriting, preserve the user's intent and voice; include a brief note only for conventions or assumptions that affect reuse.

When a HumanPy Lite script or fenced block is detected, validate its overall
structure before interpreting or rewriting it. Every meaningful line must be
clearly classified as recognized HumanPy Lite structure or plain English
instruction/prose. Report validation errors when a line is malformed,
ambiguous, or code-like without being valid HumanPy Lite. Do not report a
validation error merely because a line is not Python-like when it can be
clearly interpreted as an English instruction.

For longer workflows, build a lightweight execution map before answering:
inputs/placeholders, variables/defaults, reusable blocks, ordered steps,
branches/loops, outputs, and unresolved material questions. Keep this map
internal unless the user asks for analysis or the map reveals a problem.

## Trigger Details

Use this skill when the task involves:

- The exact text `human-py` or `humanpy` anywhere in the session.
- A fenced code block marked as `human-py` or `humanpy`.
- HumanPy Lite or HumanPy workflow notation.
- Python-shaped English that is meant to stay non-executable.
- Markdown-native pseudocode for skills or reusable workflows.
- Variables, placeholders, lightweight `def` blocks, loops, conditions, function calls, aliases, returns, or reusable workflow steps inside non-executable workflow instructions.
- Converting informal bullets or prose into structured skill workflows.
- Reviewing HumanPy Lite for unclear variables, placeholders, scope, ambiguous control flow, or unsafe assumptions.

Do not use this skill for:

- Runnable Python code.
- General programming syntax questions.
- Executable script generation unless the user explicitly asks to convert a workflow into executable code.

## Linting and Unit Tests

When the user asks `human-py lint` or requests machine-readable analysis, run
the bundled linter:

```bash
node <path-to-this-skill>/scripts/human-py-lint.mjs lint --json --pretty <file-or->
```

The linter accepts a raw HumanPy Lite script, a Markdown file containing
`humanpy`/`human-py` fences, or stdin (`-`). Its JSON includes validation
errors, per-line classifications, unresolved placeholders, symbols, and an
execution map with inputs, defaults, functions, calls, branches, loops,
outputs, returns, and ordered steps. Omit `--json` for a short text summary.

When the user asks `run human-py unit tests`, run the bundled test runner:

```bash
node <path-to-this-skill>/scripts/run-human-py-unit-tests.mjs
```

The runner loads separate test case files from `tests/*.case.md` and checks the
HumanPy Lite validation contract, then smoke-checks the JSON linter. Report the
pass/fail summary and any failing case names.

Do not read, summarize, or load files under `tests/` during normal HumanPy Lite
work. Treat those files as unit-test fixtures that are loaded only when the
user explicitly asks to run or inspect the HumanPy unit tests.

When changing recognized HumanPy Lite syntax, update both
`references/humanpy-lite.md` and the validation test runner/fixtures, then run
the bundled unit tests.
