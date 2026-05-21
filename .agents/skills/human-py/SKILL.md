---
name: human-py
description: Use whenever the session mentions human-py or humanpy, or declares a fenced code block marked human-py or humanpy. Also use for HumanPy Lite, Python-shaped English, or non-executable Markdown workflow notation for skills. Do not use for runnable Python or general programming.
---

# HumanPy Lite Workflows

Use this skill whenever a session mentions `human-py` or `humanpy`, or declares a fenced code block marked `human-py` or `humanpy`.

Also use it for HumanPy Lite, HumanPy, and Python-shaped English workflow notation in Markdown.

Load [humanpy-lite.md](references/humanpy-lite.md) before doing any substantive HumanPy Lite work, including writing, reviewing, interpreting, normalizing, converting, or embedding the notation in another skill.

When a HumanPy Lite script or fenced block is detected, validate its overall
structure before interpreting or rewriting it. Every meaningful line must be
clearly classified as recognized HumanPy Lite structure or plain English
instruction/prose. Report validation errors when a line is malformed,
ambiguous, or code-like without being valid HumanPy Lite. Do not report a
validation error merely because a line is not Python-like when it can be
clearly interpreted as an English instruction.

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

## Unit Tests

When the user asks `run human-py unit tests`, run the bundled test runner:

```bash
node <path-to-this-skill>/scripts/run-human-py-unit-tests.mjs
```

The runner loads separate test case files from `tests/*.case.md` and checks the
HumanPy Lite validation contract. Report the pass/fail summary and any failing
case names.

Do not read, summarize, or load files under `tests/` during normal HumanPy Lite
work. Treat those files as unit-test fixtures that are loaded only when the
user explicitly asks to run or inspect the HumanPy unit tests.
