# Contract Index Scoring Rubric

Each yes answer is one point. Maximum score: 9.

1. Overlap: The contract overlaps no more than 20% with any other contract by purpose, actors, IO,
   pre-conditions, post-conditions, invariants, behavior, and alternative paths.
2. Evidence: The contract maps to existing production source or specification boundary evidence;
   tests and support code can corroborate but are not the primary anchor by default.
3. Inputs: Inputs, pre-conditions, assumptions, and actor roles are clear enough for an implementer
   to know when the contract applies.
4. Actor behavior: Every listed actor is referenced by role in Detailed behavior or Alternative
   paths, or the actor is removed, renamed, or recorded as a coverage gap.
5. Output: Outputs, post-conditions, guarantees, effects, and failure modes are clear.
6. Determinacy: Outputs and post-conditions are determined by inputs, pre-conditions, actors, the
   primary path, and any alternative paths.
7. State: Internal state and invariants are explicit when behavior depends on hidden state.
8. Value: The contract protects real user, API, maintenance, correctness, performance, security, or
   reliability value.
9. Testability: At least one concrete oracle exists, such as a scenario, negative case,
   alternative-path branch, invariant check, mutation check, runtime check, or executable test.

## Refresh Guidance

During extraction, refresh, or reconciliation, treat missing or placeholder Actors, Pre-conditions,
Post-conditions, and Alternative paths as refinement gaps to fill from evidence before accepting the
score. Also check actor-behavior alignment: if an actor does not appear by role in Detailed behavior
or Alternative paths, mutate the candidate by rewriting behavior, renaming or removing the actor, or
recording the unsupported actor as a visible gap in `COVERAGE.md`.

## Candidate Triage Guidance

Candidate production should be detector-backed: profile the project shape, build or reuse the
source-anchored boundary inventory, select candidates from detected boundaries, existing contract
evidence, and known coverage gaps, then mutate/cross over only after a real boundary candidate has
been inspected. Blind random breadth is an explicit fallback, not the default. Before dropping a weak
candidate, harvest any evidence-backed actors, pre-conditions, post-conditions, alternative paths,
invariants, validation oracles, assumptions, or coverage gaps that can strengthen another contract or
guide the next round. When a candidate starts from a source-code location, first identify plausible
code paths that hit the point by tracing inbound callers, outbound callees, or both. Prefer contract
boundaries that explain the value-delivering path; record untraced caller/callee branches or
ambiguous caller/callee branches as rejected candidates or coverage gaps.

In later phases, use the coverage frontier rather than broad rediscovery. Prioritize referenced
stale boundaries, uncovered required production/spec boundaries, unresolved coverage gaps, weak or
conflicted existing contracts, optional test/support signals, then small stable audits. Stable
covered contracts should receive only minor evidence, relationship, or wording adjustments unless
source evidence changes or a conflict proves the contract identity is wrong.

Treat tests and support code as interaction signals. They can reveal negative paths, fixtures,
expected outcomes, and validation oracles, but the candidate should be anchored to production source
or local specs unless the contract is specifically about test infrastructure.

## Merge Guidance

Merge contracts when overlap is above 20% and the merged contract remains cohesive. Do not merge
only because files are near each other.

## Split Guidance

Split a contract when it has unrelated outcomes, independent protocols, too many primary actors,
unclear IO, too many branch paths, or more than about nine combined primary and alternative behavior
steps.

## Drop Guidance

After merge/split review, drop only contracts scoring less than 5% of the current population's top
fitness score and only while the population size is greater than the user-configured minimum retained
contract count. Do not drop the bottom fifth by rank; that can remove valid contracts when the whole
population scores well. If a low-scoring contract is sole coverage for an important area, keep the
area in `COVERAGE.md` as a missing-contract guideline instead of silently deleting it.

## Stop Guidance

Use the configured stop policy. `iteration` requires a user-specified `max_iterations` and stops only
when that count is reached. `exhaustive` does not require `max_iterations`; it stops only when the
coverage frontier is complete: all required active boundaries for the coverage target are covered,
no referenced stale boundaries remain, every retained contract meets `completion_min_score`, no
actor-behavior gaps remain, no merge/split/drop candidates remain, and no unresolved `COVERAGE.md`
gap lines remain. `both` stops when either policy succeeds. Do not stop early just because ranks
stop changing. Record iteration number, replay seeds, sampled seeds, candidate outcomes, frontier
blockers, rank history, drop decisions, and stop reason in `.contract-state.json` or companion
iteration artifacts.
