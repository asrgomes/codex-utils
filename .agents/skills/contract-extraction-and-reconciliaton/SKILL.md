---
name: contract-extraction-and-reconciliaton
description:
  Use when Codex is asked to identify integration boundaries, extract or reconcile local repository
  or specification behavior as evidence-backed contract markdown, score contract quality, build a
  contract index, track missing coverage, or iterate until meaningful code/spec interactions are
  covered.
---

# Contract Extraction and Reconciliaton

## Purpose

Extract and reconcile repository behavior into small, testable contracts that help coding agents
understand what must stay true. A contract is not a broad repo summary; it is an evidence-backed
assume/guarantee description of one value-delivering interaction group.

Use extraction to create contracts from code or specs. Use reconciliation to refresh, merge, split,
drop, or align existing contracts against newer evidence, coverage gaps, and each other.

## Inputs And Outputs

Inputs:

- Local repository or source-code worktree paths. Treat the user-provided list as the complete
  extraction universe unless they explicitly expand it; pass each path as a repeated `--repo`.
- Local specification paths, such as README files, issue specs, ADRs, API docs, or test plans.
- A destination contracts folder, defaulting to `contracts/`.
- A stop policy:
  - `exhaustive` for non-stop runs: continue until the coverage frontier and quality gates are
    complete. This mode does not require `max_iterations`.
  - `iteration`: stop only at the user-specified `max_iterations`.
  - `both`: stop when either exhaustive completion or `max_iterations` is reached.
- For `iteration` or `both`, a user-specified maximum iteration count. Do not assume a default.
- A user-specified minimum retained contract count. Do not drop or prune candidates until the user
  has supplied this value; ask for it if missing.
- A coverage target, defaulting to `production-spec`: cover active production and specification
  boundaries. Use `active` to require every active detected boundary; referenced stale boundaries
  always remain blockers until reconciled.
- A completion minimum score, defaulting to 8, for exhaustive completion.

Outputs:

- One contract markdown file per contract in the contracts folder.
- `.boundary-inventory.json` with reusable source-anchored project boundaries.
- `INDEX.md` with score, overlap, and relationship summaries.
- `COVERAGE.md` with covered areas and missing interaction areas. Use unchecked checklist lines
  (`- [ ] ...`) or bullet lines beginning with `Gap`, `Missing`, `Uncovered`, `Unknown`, or `TODO`
  for unresolved gaps so exhaustive completion can track them.
- `.contract-state.json` for iteration count, replay seeds, rank history, and convergence
  bookkeeping, including frontier history, sampled boundary counts, and stop-policy parameters.
- A final process summary naming iterations run, candidates created/reconciled, contracts kept,
  contracts dropped or converted to gaps, rank changes, and the stop reason.

Use only local read/write operations unless the user explicitly authorizes network, branch, commit,
or PR work.

## Contract Shape

Create one `.md` file per contract. Use `assets/contract-template.md` as the shape and keep these
fields present:

- Unique id
- Name, on one line
- Tags
- Covered boundaries, naming source boundary ids such as `boundary-...` when available
- Qualified links to other contracts, such as `relates to`, `depends on`, `is depended on by`,
  `refines`, or `conflicts with`
- Purpose
- Actors
- Inputs
- Pre-conditions
- Output
- Post-conditions
- Internal state
- Invariants
- Detailed behavior
- Alternative paths
- Evidence
- Validation

Prefer stable ids like `contract-<repo>-<area>-<short-hash>`. Do not change an id unless the
contract identity changes.

Every contract should cover the smallest cohesive interaction group, not a file, class, package, or
endpoint by default. It may list multiple covered boundaries only when the same assumptions,
guarantees, actors, validation oracle, and value-delivering behavior explain those boundaries
together. If two boundaries share files but have different actors, inputs, guarantees, failure
modes, or oracles, keep them separate and link them.

Evidence should include both human-readable source links and machine-trackable boundary evidence
when available: `boundary_id`, path and line range, matcher type, snippet hash, and the claim that
evidence supports. This lets later runs distinguish stable contracts from changed, stale, uncovered,
or weakly covered frontier work.

Actors list every external party that participates in the contract interaction, including users,
clients, peer modules, services, the operating system, storage, schedulers, and network
dependencies. Name actors as stable roles from the contract's point of view, such as
`Calling client`, `Persistent store`, `External API provider`, `Scheduler`, or `Human operator`.
Keep wording consistent across contracts; prefer the actor's role over a product, class, or vendor
identity unless that identity is itself the role.

Inputs name the values, requests, events, and environmental facts supplied to the interaction.
Pre-conditions name the required assumptions that make the contract applicable. Output names the
observable result, side effect, or failure mode. Post-conditions name the guarantees that must hold
after the interaction completes. Keep `Pre-conditions` and `Post-conditions` as explicit sections;
missing or placeholder sections reduce the existing input/output score checks.

Detailed behavior describes the primary path. Name every participating actor by its role in the
behavior text. If an actor is listed but never appears in Detailed behavior or Alternative paths,
treat that as evidence the actor is unrelated, misnamed, too broad, or missing from the behavioral
description. Alternative paths describe deviations from the primary path, including invalid inputs,
fallbacks, retries, conflicts, missing dependencies, and failure branches. Each alternative path
should name its trigger, participating actor when relevant, and observable outcome.

## Exhaustive Structure-Aware Refinement Loop

Run extraction or reconciliation as a checkpointed iterative loop over the complete input worktree
list. When the user requests a non-stop or exhaustive run, use `stop_policy=exhaustive`: do not stop
for token usage, rank stability, or lack of dramatic changes. Keep writing `.contract-state.json`,
`INDEX.md`, `COVERAGE.md`, and contract files so the run can resume from durable state if the
conversation compacts or execution is interrupted.

Every iteration begins with structure-aware candidate input before any scoring or stop decision. Use
project profiling and `scripts/boundary_inventory.py` to identify the repository shape first, then
select candidates from source-anchored boundaries, existing contract evidence, and `COVERAGE.md`
gaps. Blind random breadth discovery is disabled by default; use `candidate_seeds.py --random-count
N` only as an explicit exploratory fallback.

The boundary inventory should be opinionated toward common project shapes and coding patterns:

- Maven and Gradle: root and module build files, source/test roots, controllers, repositories,
  message listeners, scheduled jobs, servlets/filters, CLIs, and resource/config boundaries.
- Go: `go.mod`, packages, `cmd/`, `internal/`, HTTP handlers, workers, file/database/message
  boundaries, timers, and OS signal handling.
- Python: `pyproject.toml`, package layout, `src/`, scripts, FastAPI/Flask routes, Click/Typer or
  argparse CLIs, Celery/tasks, file/database/message boundaries, and schedulers.
- TypeScript: `package.json`, workspace config, `tsconfig`, app/pages/routes, Express/Nest routes,
  UI actions, CLIs, file/database/message boundaries, timers, and process signals.

Tests are discovery and validation signals, not default contract anchors. Treat obvious test
conventions such as `src/test`, `tests/`, Go `*_test.go`, Python `test_*.py`, JS/TS `*.test.*` or
`*.spec.*`, and shell/Bats tests as `test_signal`. Also classify mock, fake, stub, fixture, testkit,
harness, simulator, or in-memory support code as `support_code` even under production-looking roots
such as `src/main`. Use these files to reveal interactions, negative cases, fixtures, and oracles;
anchor contracts to production source or local specs unless the contract is explicitly about test
infrastructure.

When the runtime policy and the user explicitly allow agent delegation, run independent agents in
parallel for disjoint worktree, ecosystem, boundary, depth, reconciliation, or critic slices. Keep
each write scope independent and have the coordinating agent integrate results into final contract
files, `INDEX.md`, `COVERAGE.md`, and `.contract-state.json` to avoid write conflicts.

### Frontier Model

Maintain a frontier instead of repeatedly rediscovering the whole project. Each boundary or contract
is in one of these states:

- `uncovered-required-boundary`: active production/spec boundary required by the coverage target and
  not referenced by any contract boundary id, snippet hash, or path/line evidence.
- `uncovered-production-or-spec-boundary`: production/spec boundary outside the current target or
  not yet selected.
- `uncovered-test-or-support-signal`: test/support evidence that can improve validation but should
  not become the primary anchor unless the contract is about test infrastructure.
- `referenced-stale-boundary`: a contract still cites, by exact boundary id or hash, a boundary
  whose source hash, snippet hash, matcher, or file status changed. Reconcile these before adding
  unrelated breadth.
- `quality-frontier`: existing contracts with score below `completion_min_score`, actor-behavior
  gaps, weak evidence, weak validation, merge/split/drop candidates, unresolved `COVERAGE.md` gaps,
  or relationship conflicts.
- `stable-covered`: covered boundaries whose evidence, assumptions, guarantees, and score remain
  stable. Do not rewrite these except for small evidence, link, or wording corrections; sample a few
  only as audits.

Late-phase runs should be dominated by stale, uncovered, and quality-frontier work. Stable contracts
solidify over time and should suffer only minor adjustments unless source evidence changes or a
reconciliation conflict proves the identity is wrong.

### Iteration Order

Every iteration follows this order:

1. Profile all input worktrees and specs. Prefer `git ls-files`, `rg --files`, build manifests,
   package/module manifests, public entrypoints, controllers/handlers, clients, persistence schemas,
   configs, serialization/protocol boundaries, scheduled jobs, CLIs, and executable tests. Use
   `scripts/repo_inventory.py --profile` when a deterministic JSON profile is useful.
2. Refresh or reuse the boundary inventory for the full worktree list. Use
   `scripts/boundary_inventory.py --contracts contracts --reuse --write`. Reuse unchanged boundaries
   when path, source hash, snippet hash, and matcher version still match; mark disappeared or
   changed entries as stale instead of silently deleting them.
3. Compute the current frontier. Use previous `.contract-state.json`, `.boundary-inventory.json`,
   existing contract boundary ids/path-line evidence, `INDEX.md`, and `COVERAGE.md` to classify
   required uncovered boundaries, referenced stale boundaries, stable covered areas, and quality
   work.
4. Select candidate seeds with `scripts/candidate_seeds.py --mode frontier`. Prioritize, in order:
   referenced stale boundaries, uncovered required production/spec boundaries, unresolved coverage
   gaps, low-score or conflicted existing contracts, uncovered optional support/test signals that
   strengthen validation, then a small stable audit sample. Use sampled boundary counts in state to
   avoid cycling on the same covered areas.
5. Draft or refresh embryonic candidates from the selected seeds and retained population. Good
   groups have one coherent purpose, clear actors, inputs, pre-conditions, outputs,
   post-conditions, invariants, behavior, alternative paths, evidence, and validation. When a seed is
   a source location, identify plausible code paths that hit it before proposing the contract
   boundary. Trace inbound caller trees, outbound callee trees, or both, depending on which direction
   explains the value-delivering interaction. Record untraced branches as gaps or rejected candidate
   notes.
6. Mutate candidates one meaningful dimension at a time: narrow or expand scope, rename actors as
   roles, add or remove an actor, split primary and alternative paths, replace weak evidence, add
   pre-conditions, add post-conditions, add invariants, strengthen validation oracles, or turn an
   unsupported claim into a coverage gap.
7. Cross over candidates only when fragments improve one coherent interaction: actor roles from one,
   evidence from another, alternative-path triggers, pre-conditions, post-conditions, invariants,
   validation oracles, or coverage-gap notes. Do not cross over unrelated outcomes just because files
   are near each other.
8. Reconcile against existing contracts using scalable neighborhoods first: same boundary id, same
   path/line range, shared actor roles, shared inputs/outputs, shared tags, relationship links, or
   overlap candidates from `contract_index.py`. Merge duplicates, split multi-interaction contracts,
   preserve explicit conflict links when behavior really conflicts, and convert unsupported claims
   into coverage gaps. Avoid global rewrites of stable-covered contracts.
9. Score and rank with `scripts/contract_index.py`. Fitness includes score, overlap, merge/split/drop
   candidates, actor-behavior gaps, coverage frontier, evidence quality, and oracle strength. Every
   listed actor must be referenced by role in Detailed behavior or Alternative paths; otherwise
   mutate the behavior, rename the actor, remove the actor, or record a coverage gap. Record the
   ranked table and frontier for this iteration in `.contract-state.json`.
10. Select retained contracts. Keep the highest-fitness, least-overlapping contracts that preserve
    coverage diversity. If two contracts overlap above 20%, consider merging them unless they have
    distinct assumptions, guarantees, actors, or test oracles. If a contract has unrelated outcomes,
    unclear IO, too many actors, or too many independent interactions, split it. Drop only contracts
    whose fitness is below 5% of the current population's top fitness score and only while the
    population size remains greater than the user-configured minimum retained contract count.
    Preserve a low-scoring contract as a missing-coverage note when it is the only contract for a
    meaningful area.
11. Harvest before discarding. Move useful evidence-backed fragments into surviving contracts or
    `COVERAGE.md`: actor roles, alternative-path triggers and outcomes, evidence links,
    pre-conditions, post-conditions, invariants, validation ideas, assumptions, or missing
    interaction areas. Record candidate outcomes for the iteration: seeds sampled, candidates
    drafted, contracts added, contracts changed, contracts rejected, contracts converted to gaps,
    and evidence slices inspected.
12. Test the stop condition and either continue or finalize:
    - `exhaustive`: stop only when the coverage frontier reports complete: all required active
      boundaries for the coverage target are covered, no referenced stale boundaries remain, every
      retained contract meets `completion_min_score`, no actor-behavior gaps remain, no merge/split/
      drop candidates remain, and no unresolved `COVERAGE.md` gap lines remain.
    - `iteration`: stop only when `max_iterations` is reached.
    - `both`: stop when either condition is reached.

If no stop condition is met, return to step 1 with selected candidates plus harvested gaps as the
next population. If a stop condition is met, write `INDEX.md`, `COVERAGE.md`, and
`.contract-state.json`, then report a concise summary of the whole process.

Rank-affecting changes include contract additions/removals, id changes, score changes, ranking-order
changes, merge/split/drop decisions, overlap changes that alter those decisions, fitness-check
changes, relationship changes that alter ranking, or frontier blocker changes. Non-rank content
edits, harvested fragments, stable audit notes, and coverage-gap changes should still be recorded.
Rank changes are diagnostics for review and selection; they do not stop an exhaustive loop.

## Scoring

Use the 0-9 rubric in `references/scoring-rubric.md`. The short version is one point each for:

- overlap no more than 20%
- maps to existing production source or specification boundary evidence
- inputs and pre-conditions are clear
- actors are referenced by role in behavior or alternative-path text
- output and post-conditions are clear
- output and post-conditions follow from inputs, pre-conditions, and described interactions
- internal state/invariants are explicit when relevant
- adds real value
- is testable

Treat testability as oracle strength, not just the existence of tests. A strong contract names
scenarios, negative cases, invariant checks, mutation checks, or runtime checks.

## Literature Grounding

Use `references/literature-grounding.md` when deciding how strict the contracts should be. The
operating rule is: keep contracts compact like behavioral interface specs, evidence-backed like
specification inference, and testable like agent behavioral contracts.

## Helper Scripts

Create a deterministic project/file inventory:

```bash
python3 skills/contract-extraction-and-reconciliaton/scripts/repo_inventory.py \
  --repo . \
  --spec README.md \
  --profile \
  --output contracts/.inventory.json
```

Create or refresh the reusable boundary inventory:

```bash
python3 skills/contract-extraction-and-reconciliaton/scripts/boundary_inventory.py \
  --repo . \
  --contracts contracts \
  --reuse \
  --write
```

Select boundary-backed candidate seeds:

```bash
python3 skills/contract-extraction-and-reconciliaton/scripts/candidate_seeds.py \
  --repo . \
  --spec README.md \
  --contracts contracts \
  --count 12 \
  --mode frontier \
  --coverage-target production-spec \
  --stable-audit-count 1 \
  --state contracts/.contract-state.json \
  --write-state
```

Add blind random breadth only when explicitly needed:

```bash
python3 skills/contract-extraction-and-reconciliaton/scripts/candidate_seeds.py \
  --repo . \
  --contracts contracts \
  --count 12 \
  --random-count 2
```

Score and index contracts:

```bash
python3 skills/contract-extraction-and-reconciliaton/scripts/contract_index.py contracts \
  --coverage contracts/COVERAGE.md \
  --state contracts/.contract-state.json \
  --stop-policy exhaustive \
  --coverage-target production-spec \
  --completion-min-score 8 \
  --min-contracts <user-specified-minimum-retained-contracts> \
  --candidate-outcome "<sampled seed outcome: added, changed, rejected, or converted to gap>" \
  --write-state \
  --write-index
```

For iteration-bounded runs, use `--stop-policy iteration --max-iterations
<user-specified-max-iterations>`. For a bounded safety cap plus exhaustive completion, use
`--stop-policy both --max-iterations <user-specified-max-iterations>`.

`repo_inventory.py`, `boundary_inventory.py`, and `contract_index.py` are deterministic for unchanged
inputs. `candidate_seeds.py` is frontier-first, prints the replay seed in its JSON output, accepts
`--seed` for replay, uses no blind random breadth unless `--random-count` is set, tracks sampled
boundary counts in `.contract-state.json`, and can append the seed with `--state ... --write-state`.
`contract_index.py` writes the coverage frontier and supports `iteration`, `exhaustive`, and `both`
stop policies. All helper scripts operate only on local files.
