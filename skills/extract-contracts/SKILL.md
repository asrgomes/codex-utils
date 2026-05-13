---
name: extract-contracts
description:
  Use when Codex is asked to identify integration boundaries, extract or reconcile local repository
  or specification behavior as evidence-backed contract markdown, score contract quality, build a
  contract index, track missing coverage, or iterate until meaningful code/spec interactions are
  covered.
---

# Extract and Reconcile Contracts

## Purpose

Extract and reconcile repository behavior into small, testable contracts that help coding agents
understand what must stay true. A contract is not a broad repo summary; it is an evidence-backed
assume/guarantee description of one value-delivering interaction group.

Use extraction to create contracts from code or specs. Use reconciliation to refresh, merge, split,
prune, or align existing contracts against newer evidence, coverage gaps, and each other.

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

## Evolutionary Refinement Loop

Run extraction or reconciliation refinement like a small genetic algorithm. Keep a population of
candidate contracts, create variation through mutation and crossover, score fitness, select the best
candidates, harvest useful fragments from rejected candidates, and repeat until the stop condition
is reached.

Run this loop with multiple agents concurrently whenever the runtime and user authorization allow
agent delegation. Use concurrency to explore alternative contract boundaries, evidence slices,
assumptions, guarantees, and reconciliation decisions in parallel; do not serialize independent
candidate exploration when agents are available. Keep each agent's scope independent and
self-contained, and have the coordinating agent integrate results into final contract files,
`INDEX.md`, `COVERAGE.md`, and `.contract-state.json` to avoid write conflicts.

For each round, fan out as many independent agents as practical:

- Breadth extraction agents sample unrelated files, specs, tests, configs, and entrypoints.
- Depth extraction agents follow one high-value candidate into nearby callers, callees, tests, and
  linked specs.
- Reconciliation agents compare existing contracts against fresh evidence, overlap, merge/split
  candidates, and coverage gaps.
- Critic agents score candidate alternatives, identify weak pre-conditions or post-conditions, and
  propose evidence-backed mutations before selection.

Merge the concurrent results by scoring all returned alternatives together. Preserve distinct
contracts when alternatives have different assumptions, guarantees, actors, or validation oracles;
otherwise cross over the strongest fragments and prune duplicates.

1. Inventory the code and specs. Prefer:
   - `rg --files`
   - `git ls-files`
   - public API files, tests, docs, configs, persistence schemas, command entrypoints, protocol
     clients, adapters, parsers, serializers, caches, and state machines
   - `scripts/repo_inventory.py` when a deterministic JSON inventory is useful
2. Generate the initial population. At the start of every refinement or refresh iteration, use
   `scripts/candidate_seeds.py` or a manual equivalent to sample fresh random breadth and depth
   seeds, log the replay seed, and avoid a fixed selection order. Breadth seeds come from unrelated
   random files, specs, tests, configs, and entrypoints. Depth seeds come from existing contract
   evidence, high-value candidates, nearby callers/callees, specs linked to sampled code, and
   `COVERAGE.md` gaps.
3. Draft embryonic candidates from the population. Identify integration groups that deliver value
   together. Good groups have a coherent purpose, clear actors, clear inputs, pre-conditions,
   outputs, post-conditions, and observable behavior.
4. Mutate candidates. Change one meaningful dimension at a time: narrow or expand scope, rename
   actors as roles, add or remove an actor, split primary and alternative paths, replace weak
   evidence, add pre-conditions, add post-conditions, add invariants, strengthen validation oracles,
   or turn an unsupported claim into a coverage gap.
5. Cross over candidates. Combine useful fragments from two candidates when they improve one
   coherent interaction: actor roles from one, evidence from another, alternative-path triggers,
   pre-conditions, post-conditions, invariants, validation oracles, or coverage-gap notes. Do not
   cross over unrelated outcomes just because files are near each other.
6. Score fitness with `scripts/contract_index.py`. Fitness includes score, overlap,
   merge/split/prune candidates, actor-behavior gaps, coverage gaps, evidence quality, and oracle
   strength. Every listed actor must be referenced by role in Detailed behavior or Alternative
   paths; otherwise mutate the behavior, rename the actor, remove the actor, or record a coverage
   gap.
7. Select candidates. Keep the highest-fitness, least-overlapping contracts that preserve coverage
   diversity. If two contracts overlap above 20%, consider merging them unless they have distinct
   assumptions, guarantees, or test oracles. If a contract has unrelated outcomes, unclear IO, too
   many actors, or too many independent interactions, split it. Prune only contracts scoring less
   than 20% of the current population's maximum score; do not prune the bottom fifth by rank. Preserve
   a low-scoring contract as a missing-coverage note when it is the only contract for a meaningful area.
8. Harvest before discarding. Before rejecting a weak candidate, move useful evidence-backed
   fragments into surviving contracts or `COVERAGE.md`: actor roles, alternative-path triggers and
   outcomes, evidence links, pre-conditions, post-conditions, invariants, validation ideas,
   assumptions, or missing interaction areas.
9. Repeat. Use selected candidates plus harvested gaps as the next population. Stop only after two
   consecutive rounds have no material changes. Use an 8-round hard cap and write an unresolved
   convergence note if it is reached.

Material changes include contract additions/removals, id changes, score changes, fitness-check
changes, merge/split decisions, relationship changes, actor-list changes, actor-behavior-reference
changes, pre-condition changes, post-condition changes, alternative-path changes,
harvested-fragment changes, or coverage-gap changes.

## Scoring

Use the 0-9 rubric in `references/scoring-rubric.md`. The short version is one point each for:

- overlap no more than 20%
- maps to existing code/spec evidence
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

Create an inventory:

```bash
python3 skills/extract-contracts/scripts/repo_inventory.py --repo . --spec README.md --output contracts/.inventory.json
```

Select randomized candidate seeds:

```bash
python3 skills/extract-contracts/scripts/candidate_seeds.py \
  --repo . \
  --spec README.md \
  --contracts contracts \
  --count 12
```

Score and index contracts:

```bash
python3 skills/extract-contracts/scripts/contract_index.py contracts \
  --coverage contracts/COVERAGE.md \
  --state contracts/.contract-state.json \
  --write-state \
  --write-index
```

`repo_inventory.py` and `contract_index.py` are deterministic. `candidate_seeds.py` uses fresh
randomness by default, prints the replay seed in its JSON output, accepts `--seed` for replay, and
operates only on local files.
