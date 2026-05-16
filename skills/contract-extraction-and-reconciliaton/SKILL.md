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

- Local repository paths.
- Local specification paths, such as README files, issue specs, ADRs, API docs, or test plans.
- A destination contracts folder, defaulting to `contracts/`.
- A user-specified maximum iteration count. Do not start a long-running refinement loop until the
  user has supplied this value; ask for it if missing.
- A user-specified minimum retained contract count. Do not drop or prune candidates until the user
  has supplied this value; ask for it if missing.

Outputs:

- One contract markdown file per contract in the contracts folder.
- `.boundary-inventory.json` with reusable source-anchored project boundaries.
- `INDEX.md` with score, overlap, and relationship summaries.
- `COVERAGE.md` with covered areas and missing interaction areas.
- `.contract-state.json` for iteration count, replay seeds, rank history, and convergence
  bookkeeping.
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

## Structure-Aware Refinement Loop

Run extraction or reconciliation refinement as a long-running iterative loop. The user must specify
`max_iterations`; never assume a default for a long run. Keep a population of candidate contracts,
create variation through mutation and crossover, reconcile duplicates and inconsistencies, score and
rank fitness, drop only candidates below the retained-count threshold, and repeat until the stop
condition is reached.

Every iteration must begin with structure-aware candidate input before any scoring or stop decision.
Use project profiling and `scripts/boundary_inventory.py` to identify the repository shape first,
then select candidates from reusable source-anchored boundaries, existing contract evidence, and
`COVERAGE.md` gaps. Blind random breadth discovery is disabled by default because it is inefficient
in large projects; use `candidate_seeds.py --random-count N` only when a deliberate exploratory
fallback is needed.

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

Run this loop with multiple agents concurrently whenever the runtime and user authorization allow
agent delegation. Use concurrency to explore alternative contract boundaries, evidence slices,
assumptions, guarantees, and reconciliation decisions in parallel; do not serialize independent
candidate exploration when agents are available. Keep each agent's scope independent and
self-contained, and have the coordinating agent integrate results into final contract files,
`INDEX.md`, `COVERAGE.md`, and `.contract-state.json` to avoid write conflicts.

For each round, fan out as many independent agents as practical. Prefer self-contained structure
probes by ecosystem before drafting contracts:

- Project-structure agents identify Maven, Gradle, Go, Python, and TypeScript modules/packages,
  main patterns, test/support conventions, and detector scope.
- Boundary extraction agents inspect one boundary class or ecosystem slice from the inventory.
- Depth extraction agents follow one high-value candidate into nearby callers, callees, production
  evidence, test signals, and linked specs.
- Reconciliation agents compare existing contracts against fresh evidence, overlap, merge/split
  candidates, and coverage gaps.
- Critic agents score candidate alternatives, identify weak pre-conditions or post-conditions, and
  propose evidence-backed mutations before selection.

Merge the concurrent results by scoring all returned alternatives together. Preserve distinct
contracts when alternatives have different assumptions, guarantees, actors, or validation oracles;
otherwise cross over the strongest fragments and drop duplicates.

Every iteration follows this order:

1. Profile the code and specs. Prefer `git ls-files`, `rg --files`, build manifests, package/module
   manifests, public entrypoints, controllers/handlers, clients, persistence schemas, configs,
   serialization/protocol boundaries, scheduled jobs, CLIs, and executable tests. Use
   `scripts/repo_inventory.py --profile` when a deterministic JSON profile is useful.
2. Refresh or reuse the boundary inventory. Use `scripts/boundary_inventory.py --contracts
   contracts --reuse --write` to persist `contracts/.boundary-inventory.json`. Reuse unchanged
   boundaries when their path, source hash, snippet hash, and matcher version still match; mark
   disappeared or changed entries as stale instead of silently deleting them.
3. Create candidate seeds from the boundary inventory and known gaps. Use
   `scripts/candidate_seeds.py` to select source-anchored boundary seeds, existing contract-evidence
   depth seeds, and `COVERAGE.md` gap seeds. Treat the seed list as work to perform, not
   bookkeeping. Use `--random-count N` only when explicitly choosing blind random exploration.
4. Draft embryonic candidates from the selected seeds and the retained population. Identify
   integration groups that deliver value
   together. Good groups have a coherent purpose, clear actors, clear inputs, pre-conditions,
   outputs, post-conditions, and observable behavior. When a fresh seed is a source-code location,
   identify plausible code paths that hit that point before proposing the contract boundary. Trace
   inbound caller trees, outbound callee trees, or both, depending on which direction explains the
   value-delivering interaction. Record the chosen path evidence and note any important untraced
   caller/callee branches as coverage gaps or rejected candidate notes.
5. Mutate candidates. Change one meaningful dimension at a time: narrow or expand scope, rename
   actors as roles, add or remove an actor, split primary and alternative paths, replace weak
   evidence, add pre-conditions, add post-conditions, add invariants, strengthen validation oracles,
   or turn an unsupported claim into a coverage gap.
6. Cross over candidates. Combine useful fragments from two candidates when they improve one
   coherent interaction: actor roles from one, evidence from another, alternative-path triggers,
   pre-conditions, post-conditions, invariants, validation oracles, or coverage-gap notes. Do not
   cross over unrelated outcomes just because files are near each other.
7. Reconcile contracts. Compare candidates and existing contracts for duplicate identity,
   inconsistent assumptions or guarantees, conflicting actors, overlap, missing evidence, and
   incoherent scope. Merge duplicates, split multi-interaction contracts, keep explicit conflict
   links when real behavior conflicts, and convert unsupported claims into coverage gaps.
8. Score and rank fitness with `scripts/contract_index.py`. Fitness includes score, overlap,
   merge/split/drop candidates, actor-behavior gaps, coverage gaps, evidence quality, and oracle
   strength. Every listed actor must be referenced by role in Detailed behavior or Alternative
   paths; otherwise mutate the behavior, rename the actor, remove the actor, or record a coverage
   gap. Record the ranked table for this iteration in `.contract-state.json`.
9. Select candidates. Keep the highest-fitness, least-overlapping contracts that preserve coverage
   diversity. If two contracts overlap above 20%, consider merging them unless they have distinct
   assumptions, guarantees, or test oracles. If a contract has unrelated outcomes, unclear IO, too
   many actors, or too many independent interactions, split it. Drop only contracts whose fitness is
   below 5% of the current population's top fitness score and only while the population size remains
   greater than the user-configured minimum retained contract count. Preserve a low-scoring contract
   as a missing-coverage note when it is the only contract for a meaningful area.
10. Harvest before discarding. Before rejecting a weak candidate, move useful evidence-backed
   fragments into surviving contracts or `COVERAGE.md`: actor roles, alternative-path triggers and
   outcomes, evidence links, pre-conditions, post-conditions, invariants, validation ideas,
   assumptions, or missing interaction areas. Record candidate outcomes for the iteration: seeds
   sampled, candidates drafted, contracts added, contracts changed, contracts rejected, contracts
   converted to gaps, and evidence slices inspected.
11. Test the stop condition. Stop when either:
    - the iteration count reaches the user-specified `max_iterations`.

If neither stop condition is met, return to step 1 with selected candidates plus harvested gaps as
the next population. If a stop condition is met, write `INDEX.md`, `COVERAGE.md`, and
`.contract-state.json`, then report a concise summary of the whole process.

Rank-affecting changes include contract additions/removals, id changes, score changes, ranking-order
changes, merge/split/drop decisions, overlap changes that alter those decisions, fitness-check
changes, or relationship changes that alter ranking. Non-rank content edits, harvested fragments,
and coverage-gap changes should still be recorded. Rank changes are diagnostics for review and
selection; they do not stop the loop before `max_iterations`.

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
  --max-iterations <user-specified-max-iterations> \
  --min-contracts <user-specified-minimum-retained-contracts> \
  --candidate-outcome "<sampled seed outcome: added, changed, rejected, or converted to gap>" \
  --write-state \
  --write-index
```

`repo_inventory.py`, `boundary_inventory.py`, and `contract_index.py` are deterministic for unchanged
inputs. `candidate_seeds.py` is inventory-first, prints the replay seed in its JSON output, accepts
`--seed` for replay, uses no blind random breadth unless `--random-count` is set, and can append the
seed to `.contract-state.json` with `--state ... --write-state`. All helper scripts operate only on
local files.
