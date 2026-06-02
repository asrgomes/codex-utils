# Codex Operating Loop

## Evidence First

Use independent reads in parallel where possible: `git status`, `git branch --show-current`, `git rev-parse HEAD`, helper `status`, and helper `branch-info` can usually run before editing. Use `multi_tool_use.parallel` for independent file reads and repo/Jenkins evidence collection.

Jenkins evidence belongs under `/tmp`, not in the tracked repository. Keep the evidence directory path in progress updates so it can be inspected later.

## Sandbox And Network

Use the helper script or `curl --globoff` for Jenkins API reads. If a Jenkins network command fails with a sandbox-like network error and the command is needed, retry with `require_escalated` and a concise approval question. Do not ask separately before the tool escalation; use the tool's approval flow.

## Git Safety

Read the worktree before editing:

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git diff --name-only
```

Do not switch branches, create a worktree, rewrite history, reset, clean, delete files, or overwrite unrelated user changes without explicit approval. If unrelated dirty changes overlap files needed for the fix, ask how to proceed.

Commit only intended changes. Before committing, run focused verification, `git diff --check`, and inspect the diff for security regressions. If the ticket or commit message is not inferable from branch/history/context, ask.

## Progress Updates

During long waits, provide short updates with build number, result/building state, elapsed time, and whether the expected SHA has appeared. Do not end the turn while a required poll, test, push, or Jenkins wait command is still running.

## Stop Conditions

Stop and ask when the next action is unclear or risky. Continue without asking when the evidence points to a narrow, reversible local fix and the worktree is clean or the edited files are clearly yours.
