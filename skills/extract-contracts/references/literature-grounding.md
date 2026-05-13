# Literature Grounding

Use these findings to keep extracted and reconciled contracts useful for coding agents.

## Behavioral Contracts

- Design by Contract and behavioral interface specification languages use preconditions,
  postconditions, invariants, and assertions to make component obligations explicit.
- JML shows how this idea applies to Java modules: contracts document behavior at boundaries and
  support assertion checking, unit testing, and static verification.
- Contract-based component design favors assume/guarantee thinking: assumptions describe the
  environment and inputs; guarantees describe outputs and behavior when assumptions hold.

## Inference And Validation

- Daikon-style invariant inference shows that useful invariants can be extracted from programs, but
  inferred invariants need evidence and validation because they may be overfit to observed behavior.
- NL2Contract-style work shows that postconditions alone are not enough; preconditions reduce false
  alarms and clarify when guarantees apply.
- LLM contract-generation work reports that explicit preconditions and postconditions improve code
  generation accuracy compared with natural-language-only prompts.

## Coding-Agent Implications

- Specification inference can improve coding agents when it is iterative, evidence-backed, and
  reviewed against code behavior.
- Runtime and test-driven agent-contract work emphasizes measurable compliance, hidden or negative
  cases, mutation-style checks, and regression safety.
- Repository context files can reduce coding-agent success when they add unnecessary broad
  instructions. Keep contracts compact, local to a behavior, and directly actionable.

## Practical Rule

Extract or reconcile the smallest contract that preserves a meaningful interaction. Expand only when
the extra detail improves assumptions, guarantees, invariants, evidence, or validation.
