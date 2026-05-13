---
name: extract-contracts
description: Extract compact, evidence-backed behavioral contracts from one or more local git repositories and specification files. Use when Codex is asked to autonomously identify integration boundaries, summarize behavior as contract markdown, score contract quality, build a contract index, track missing coverage, or iterate until meaningful code/spec interactions are covered.
---

# Extract Contracts

## Purpose

Extract repository behavior into small, testable contracts that help coding agents understand what must stay true. A contract is not a broad repo summary; it is an evidence-backed assume/guarantee description of one value-delivering interaction group.

## Inputs And Outputs

Inputs:
- Local repository paths.
- Local specification paths, such as README files, issue specs, ADRs, API docs, or test plans.
- A destination contracts folder, defaulting to `contracts/`.

Outputs:
- One contract markdown file per contract in the contracts folder.
- `INDEX.md` with score, overlap, and relationship summaries.
- `COVERAGE.md` with covered areas and missing interaction areas.
- `.contract-state.json` for convergence bookkeeping.

Use only local read/write operations unless the user explicitly authorizes network, branch, commit, or PR work.

## Contract Shape

Create one `.md` file per contract. Use `assets/contract-template.md` as the shape and keep these fields present:

- Unique id
- Name, on one line
- Tags
- Qualified links to other contracts, such as `relates to`, `depends on`, `is depended on by`, `refines`, or `conflicts with`
- Purpose
- Actors
- Inputs
- Output
- Internal state
- Invariants
- Detailed behavior
- Alternative paths
- Evidence
- Validation

Prefer stable ids like `contract-<repo>-<area>-<short-hash>`. Do not change an id unless the contract identity changes.

Actors list every external party that participates in the contract interaction, including users, clients, peer modules, services, the operating system, storage, schedulers, and network dependencies. Name actors as stable roles from the contract's point of view, such as `Calling client`, `Persistent store`, `External API provider`, `Scheduler`, or `Human operator`. Keep wording consistent across contracts; prefer the actor's role over a product, class, or vendor identity unless that identity is itself the role.

Detailed behavior describes the primary path. Name every participating actor by its role in the behavior text. If an actor is listed but never appears in Detailed behavior or Alternative paths, treat that as evidence the actor is unrelated, misnamed, too broad, or missing from the behavioral description. Alternative paths describe deviations from the primary path, including invalid inputs, fallbacks, retries, conflicts, missing dependencies, and failure branches. Each alternative path should name its trigger, participating actor when relevant, and observable outcome.

## Evolutionary Refinement Loop

Run refinement like a small genetic algorithm. Keep a population of candidate contracts, create variation through mutation and crossover, score fitness, select the best candidates, harvest useful fragments from rejected candidates, and repeat until the stop condition is reached.

1. Inventory the code and specs. Prefer:
   - `rg --files`
   - `git ls-files`
   - public API files, tests, docs, configs, persistence schemas, command entrypoints, protocol clients, adapters, parsers, serializers, caches, and state machines
   - `scripts/repo_inventory.py` when a deterministic JSON inventory is useful
2. Generate the initial population. At the start of every refinement or refresh iteration, use `scripts/candidate_seeds.py` or a manual equivalent to sample fresh random breadth and depth seeds, log the replay seed, and avoid a fixed selection order. Breadth seeds come from unrelated random files, specs, tests, configs, and entrypoints. Depth seeds come from existing contract evidence, high-value candidates, nearby callers/callees, specs linked to sampled code, and `COVERAGE.md` gaps.
3. Draft embryonic candidates from the population. Identify integration groups that deliver value together. Good groups have a coherent purpose, clear actors, clear inputs/outputs, and observable behavior.
4. Mutate candidates. Change one meaningful dimension at a time: narrow or expand scope, rename actors as roles, add or remove an actor, split primary and alternative paths, replace weak evidence, add invariants, strengthen validation oracles, or turn an unsupported claim into a coverage gap.
5. Cross over candidates. Combine useful fragments from two candidates when they improve one coherent interaction: actor roles from one, evidence from another, alternative-path triggers, invariants, validation oracles, or coverage-gap notes. Do not cross over unrelated outcomes just because files are near each other.
6. Score fitness with `scripts/contract_index.py`. Fitness includes score, overlap, merge/split/prune candidates, actor-behavior gaps, coverage gaps, evidence quality, and oracle strength. Every listed actor must be referenced by role in Detailed behavior or Alternative paths; otherwise mutate the behavior, rename the actor, remove the actor, or record a coverage gap.
7. Select candidates. Keep the highest-fitness, least-overlapping contracts that preserve coverage diversity. If two contracts overlap above 20%, consider merging them unless they have distinct assumptions, guarantees, or test oracles. If a contract has unrelated outcomes, unclear IO, too many actors, or too many independent interactions, split it. Prune the lower 20% by score, but preserve a low-scoring contract as a missing-coverage note when it is the only contract for a meaningful area.
8. Harvest before discarding. Before rejecting a weak candidate, move useful evidence-backed fragments into surviving contracts or `COVERAGE.md`: actor roles, alternative-path triggers and outcomes, evidence links, invariants, validation ideas, assumptions, or missing interaction areas.
9. Repeat. Use selected candidates plus harvested gaps as the next population. Stop only after two consecutive rounds have no material changes. Use an 8-round hard cap and write an unresolved convergence note if it is reached.

Material changes include contract additions/removals, id changes, score changes, fitness-check changes, merge/split decisions, relationship changes, actor-list changes, actor-behavior-reference changes, alternative-path changes, harvested-fragment changes, or coverage-gap changes.

## Scoring

Use the 0-9 rubric in `references/scoring-rubric.md`. The short version is one point each for:

- overlap no more than 20%
- maps to existing code/spec evidence
- inputs are clear
- actors are referenced by role in behavior or alternative-path text
- output is clear
- output follows from inputs and described interactions
- internal state/invariants are explicit when relevant
- adds real value
- is testable

Treat testability as oracle strength, not just the existence of tests. A strong contract names scenarios, negative cases, invariant checks, mutation checks, or runtime checks.

## Literature Grounding

Use `references/literature-grounding.md` when deciding how strict the contracts should be. The operating rule is: keep contracts compact like behavioral interface specs, evidence-backed like specification inference, and testable like agent behavioral contracts.

## Helper Scripts

Create an inventory:

```bash
python3 skills/extract-contracts/scripts/repo_inventory.py --repo . --spec README.md --output contracts/.inventory.json
```

Select randomized candidate seeds:

```bash
python3 skills/extract-contracts/scripts/candidate_seeds.py --repo . --spec README.md --contracts contracts --count 12
```

Score and index contracts:

```bash
python3 skills/extract-contracts/scripts/contract_index.py contracts --coverage contracts/COVERAGE.md --state contracts/.contract-state.json --write-state --write-index
```

`repo_inventory.py` and `contract_index.py` are deterministic. `candidate_seeds.py` uses fresh randomness by default, prints the replay seed in its JSON output, accepts `--seed` for replay, and operates only on local files.
