---
name: task-planning-and-execution
description:
  Plan, track, execute, verify, review, archive, and learn from non-trivial repository work. Use
  when Codex needs task tracking, worktree decisions, subagent coordination, bug fixes, failing CI
  investigation, implementation planning, verification strategy, archive cleanup, or lessons-learned
  updates for repo tasks.
---

# Task Planning and Execution

Use this workflow to keep repository work anchored to the live checkout, explicit task state, and
verified results. Keep task files practical: they are operational records, not status theater.

## Session Start

1. Re-read the user request, current instructions, and relevant repo files before acting.
2. Inspect `git branch --show-current` and `git status --short` before edits.
3. Treat existing uncommitted changes as user-owned unless you made them in this session.
4. Identify whether the work is trivial, already tracked, or needs a task entry.
5. Preserve exact issue IDs, command strings, stack traces, and file paths from the request.

## Task Files

Maintain task files only when the repo already uses them or the work needs durable tracking.

- `tasks/todo.md`: active and current work only, with `[ ]`, `[-]`, and `[x]` states.
- `tasks/archive.md`: verified completed tasks moved from `todo.md` only after the user verifies the
  solution and explicitly requests archival.
- `tasks/backlog.md`: candidate ideas, follow-ups, or speculative work not yet accepted.
- `tasks/lessons.md`: corrections and rules that prevent repeated mistakes.

Do not create task files for a meta-change unless the user asked for that tracking.

## Task IDs

Give each tracked task a stable ID in this form:

```text
`${TYPE}-${Date.now().toString(36)}`
```

Allowed `TYPE` values are `FEATURE`, `BUG`, `DOC`, `CHORE`, `REFACTOR`, and `TEST`. Keep the same ID
when moving a task between files.

## Task Definition Quality Gate

Before adding, accepting, or rewriting a task, make the task small enough to execute and verify
without hidden follow-up interpretation.

1. Anchor the task to current evidence from the live checkout, not only prior discussion or memory.
2. Write one task for one behavioral, schema, performance, docs, or workflow outcome.
3. Split a task when it mixes distinct work streams, such as lifecycle semantics, SQL shape,
   metrics, migrations, batching, and shutdown/drain behavior.
4. Split a task when the verification would need unrelated fixtures or unrelated owner areas.
5. Keep an existing task ID only when the underlying outcome is unchanged; create new IDs for split
   follow-ups.
6. Keep backlog entries candidate-shaped and todo entries execution-shaped. Do not let backlog text
   imply active ownership or completion.

Each durable task should include enough context for the next agent to start from the file alone:

- `Finding`: the current observed gap, with exact classes, paths, or symptoms when known.
- `Pressure mode`: why this matters under realistic load, failure, migration, or operator behavior.
- `Candidate`: the smallest plausible change family, not a full design unless the task is a design
  task.
- `Verify`: deterministic commands, tests, fixtures, or evidence that would prove the task's actual
  claim.

Avoid weak verification language:

- Do not say "run existing tests" when the existing tests only prove general behavior.
- Do not use an abstract test class as the executable target; name concrete subclasses or another
  runnable entry point.
- For performance or refactor tasks, require a fixture or assertion that proves the intended
  property, such as bounded wait time, SQL shape, batching, statement reuse, or emitted metrics.
- For plan-sensitive tasks, require deterministic plan evidence or stable SQL-shape assertions
  instead of an ad hoc copied `EXPLAIN` snippet.

Database-facing tasks require explicit database scope.

- If a task touches SQL, schema, migrations, indexes, locking, query plans, JDBC behavior, or
  transaction-manager database code, it must state how both MySQL and Oracle are handled.
- A database task may be single-dialect only when the title and body explicitly say the other
  dialect is unaffected, deferred, or covered by a separate task.
- Verification must name concrete MySQL and Oracle checks for shared database behavior. In this
  repo, prefer `MysqlSfpTransactionManagerTest` and `OracleSfpTransactionManagerTest` over
  `BaseSfpTransactionManagerTest`.
- Schema/model changes should separate migration/index work from hot-query behavior when each part
  needs different rollout or verification evidence.

Before finishing a task-file edit, re-read the file as a backlog/todo/archive set:

1. Remove or update stale header claims after tasks move between backlog, todo, and archive.
2. Confirm completed items are not duplicated as open backlog work.
3. Confirm task order still matches the priority statement.
4. Confirm every database-facing open task names both MySQL and Oracle scope or clearly explains why
   it does not.

## Planning Gate

Before implementation, make the smallest useful plan when the work is non-trivial.

1. Define the user-visible outcome and the files or modules likely involved.
2. Record open decisions only when they affect behavior, data, risk, or verification.
3. Prefer the repo's established patterns over new abstractions.
4. Choose the most specific deterministic verification command available.
5. Update `tasks/todo.md` if the repo's workflow expects tracked active work.

Skip a written plan for tiny, single-step changes, but still verify the live state first.

## Worktree Gate

Before changing files:

1. Refuse implementation if the checkout is not on a feature branch when repo rules require it.
2. Do not revert, overwrite, reformat, or stage unrelated user changes.
3. If unrelated dirty files exist, scope reads and patches to the requested work.
4. If a required file has conflicting user edits, read it carefully and work with the current state.
5. Stop and ask only when proceeding would destroy user work or require an unsafe assumption.

## Execution

1. Read the local implementation and tests that control the behavior.
2. Make narrow edits that satisfy the task and preserve existing contracts.
3. Keep comments short and only where they clarify non-obvious control flow.
4. Update related docs when behavior, workflow, or operator expectations change.
5. Update the task state from `[ ]` to `[-]` while work is active and `[x]` only after verification
   passes or the user explicitly accepts the residual risk.

## Subagents

Use subagents only when they improve independence or coverage.

- Give subagents raw artifacts and a focused objective, not your intended conclusion.
- Use them for broad review, alternate debugging hypotheses, or parallel source inspection.
- Reconcile their output against the live checkout before making changes.
- Do not delegate reading skill instructions, user instructions, or final accountability.

## Verification

Run the most specific concrete test or command that proves the change.

1. Ensure every change is covered by the nearest deterministic test, validator, or reproduction.
2. For code behavior changes, add or update tests that directly exercise the changed class or unit.
3. If unit tests already exist for a changed class, update or add that class-specific unit coverage;
   do not rely solely on higher-level integration-like tests.
4. Prefer a targeted unit test, focused integration test, linter, validator, or reproduction.
5. Never target abstract JUnit base classes directly.
6. Preserve interrupt status and exact failure output when investigating failed commands.
7. If verification fails, fix the cause or re-plan from the new evidence.
8. If verification cannot run, record the exact command, reason, and remaining risk.

## Review and Archive

Before final response or archive:

1. Re-read changed files that matter and inspect `git diff --check` where appropriate.
2. Confirm task IDs, statuses, and task-file placement are coherent.
3. Do not move completed tasks from `tasks/todo.md` to `tasks/archive.md` automatically. Keep them
   in `todo.md` until the user verifies the solution and explicitly requests archival.
4. Leave incomplete, completed-but-unarchived, blocked, or speculative items in `todo.md` or
   `backlog.md` with current state.
5. Summarize only the changes, verification, and unresolved risks that matter to the user.

## Lessons

Add or update `tasks/lessons.md` when a mistake, review finding, CI failure, or repeated correction
reveals a reusable rule.

- Write lessons as concrete rules tied to the repo or workflow.
- Include the triggering evidence when it helps future agents avoid repeating the error.
- Do not add generic lessons that restate normal engineering practice.

## Failure Re-Plan

When a test, build, review, or assumption fails:

1. Stop expanding the original implementation path.
2. Capture the failing command, error, and affected files.
3. Re-read the relevant code and task entry.
4. Adjust the plan or task state to match the new evidence.
5. Continue only after the next verification step is explicit.
