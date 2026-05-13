# Contract Index Scoring Rubric

Each yes answer is one point. Maximum score: 9.

1. Overlap: The contract overlaps no more than 20% with any other contract by purpose, actors, IO,
   pre-conditions, post-conditions, invariants, behavior, and alternative paths.
2. Evidence: The contract maps to existing code or specification evidence.
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

Candidate production should behave like an evolutionary search: generate a population from broad and
deep seeds, mutate candidates, cross over useful fragments, score fitness, select the strongest and
most diverse candidates, and repeat until stable. Before pruning a weak candidate, harvest any
evidence-backed actors, pre-conditions, post-conditions, alternative paths, invariants, validation
oracles, assumptions, or coverage gaps that can strengthen another contract or guide the next round.

## Merge Guidance

Merge contracts when overlap is above 20% and the merged contract remains cohesive. Do not merge
only because files are near each other.

## Split Guidance

Split a contract when it has unrelated outcomes, independent protocols, too many primary actors,
unclear IO, too many branch paths, or more than about nine combined primary and alternative behavior
steps.

## Prune Guidance

Prune the lower 20% by score after merge/split review. If a low-scoring contract is sole coverage
for an important area, keep the area in `COVERAGE.md` as a missing-contract guideline instead of
silently deleting it.
