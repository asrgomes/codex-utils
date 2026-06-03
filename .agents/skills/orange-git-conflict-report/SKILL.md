---
name: orange-git-conflict-report
description: "Use when the user wants a read-only HTML review report for Git merge conflicts, especially merge-conflict-review.html with current-branch vs incoming-branch panels, original stage line numbers, context, highlighted conflicting text, material-impact notes, and proposed-resolution previews before applying any conflict resolution."
---

# Orange Git Conflict Report

Use this skill when the user asks to inspect merge conflicts before resolving them, produce `merge-conflict-review.html`, or review each conflict hunk with left/right panels. The workflow is read-only for conflicted source files; only the requested report file should be created or overwritten.

## Report Contract

The report must make these labels explicit:

- **Left** is the current branch, Git index stage 2 / `HEAD`.
- **Right** is the incoming branch being merged, Git index stage 3.
- Proposed output is a review-only preview and is not applied to source files.

The report should include:

- one closed-by-default collapsible block per conflicted file
- one closed-by-default collapsible panel per conflict hunk
- stable hunk numbers for reference
- original line numbers from each revision when Git stages are available
- 15 lines of surrounding context in conflict panels and "what changed" side-by-side diffs unless the user requests another value
- whitespace-preserving code rendering
- inline highlighting of changed words/substrings when possible
- explanation of what changed on each side
- under the "what changed" explanation, a side-by-side diff for the left/current branch against the closest common ancestor
- below the left/current diff, a side-by-side diff for the right/incoming branch against the closest common ancestor
- original line numbers in those ancestor diffs, with word-level highlights for replacements
- equal-width and equal-height panels whenever two code panels are shown side-by-side
- semantic side-by-side diff colors: red for removed lines, green for added lines, yellow for changed lines
- material-impact classification, distinguishing behavior changes from formatting/style-only changes
- a proposed-resolution preview with line numbers and surrounding context
- dark mode and syntax highlighting

## Standard Workflow

1. Confirm the repository is in a merge-conflict state:

```bash
git status --short --branch
git diff --name-only --diff-filter=U
```

2. Run the bundled generator from the repository root:

```bash
python3 <skill-dir>/scripts/generate_merge_conflict_review.py --repo . --output merge-conflict-review.html
```

3. Verify the report shape:

```bash
rg -c '<details class="file-block"' merge-conflict-review.html
rg -c '<details class="hunk-panel"' merge-conflict-review.html
rg -n 'Left: current branch|Right: incoming branch|side-by-side-diff|color-scheme: dark|tok-keyword' merge-conflict-review.html
git status --short --branch
```

4. Tell the user where the report is and explicitly state that conflicted source files were not resolved or edited.

## Generator Options

Run `python3 <skill-dir>/scripts/generate_merge_conflict_review.py --help` for all options.

Common options:

```bash
python3 <skill-dir>/scripts/generate_merge_conflict_review.py --repo . --output merge-conflict-review.html --context 15
python3 <skill-dir>/scripts/generate_merge_conflict_review.py --repo . --output merge-conflict-review.html --context 15 --diff-context 15
python3 <skill-dir>/scripts/generate_merge_conflict_review.py --repo . --proposal auto
python3 <skill-dir>/scripts/generate_merge_conflict_review.py --repo . --proposal ours
python3 <skill-dir>/scripts/generate_merge_conflict_review.py --repo . --proposal theirs
python3 <skill-dir>/scripts/generate_merge_conflict_review.py --repo . --proposal union
```

`auto` is the default proposal mode. It keeps the non-empty side for one-sided conflicts, keeps the larger superset when one side already contains the other, keeps current-branch formatting for whitespace-only differences, and otherwise shows a de-duplicated union for review. This is intentionally conservative and must not be applied without user approval.

Use `--notes-json` only when the user or prior investigation supplies reviewed hunk-specific decisions. It can override summaries, material-impact text, recommendation text, and proposed lines.

The ancestor diff uses Git index stage 1 as the closest common ancestor, stage 2 as the current branch, and stage 3 as the incoming branch.

## Safety Rules

- Do not run `git checkout --ours`, `git checkout --theirs`, `git add`, `git merge --continue`, or source edits as part of report generation.
- Do not treat the automatic proposal as an approved resolution.
- If the report command fails because Git stages are unavailable, inspect whether the user has already edited away conflict state before regenerating.
- If dependencies are missing, install only what is needed. The bundled generator requires only `git` and `python3`; prefer not to install extra packages.

## Validation

When changing the helper, run:

```bash
python3 -m unittest discover <skill-dir>/tests
```
