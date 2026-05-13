# <Contract Name>

- Unique id: contract-<repo>-<area>-<hash>
- Name: <single-line name>
- Tags: <tag-one>, <tag-two>
- Links:
  - relates to: <contract-id> - <why the link matters>

## Purpose

<A few lines explaining the user or maintenance value of this contract.>

## Actors

- <Role name>: <External party and role in this contract; reference this role name in behavior
  text.>

## Inputs

- <Input value, actor request, event, or environmental fact supplied to the interaction.>

## Pre-conditions

- <Required assumptions for when this contract applies.>

## Output

- <Observable result, side effect, or failure mode.>

## Post-conditions

- <Required guarantees after the interaction completes.>

## Internal State

- <State that affects behavior but is not directly visible. Use "None known" for stateless
  behavior.>

## Invariants

- <Property that must remain true across interactions.>

## Detailed Behavior

1. <Interaction step naming participating actor role(s).>
2. <Interaction step naming participating actor role(s).>
3. <Interaction step naming participating actor role(s).>

## Alternative Paths

- <Trigger>: <Deviation from the primary path, participating actor role(s) when relevant, and
  observable outcome.>

## Evidence

- `<path>:<line>` - <claim supported by this evidence>

## Validation

- Scenario: <happy-path scenario or executable test idea>
- Negative case: <invalid input, conflict, or boundary case>
- Oracle: <how an agent or test decides the contract held>
