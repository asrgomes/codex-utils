from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "extract-contracts" / "scripts"


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_candidate_seed_labels_distinguish_same_relative_path_across_repos(tmp_path):
    candidate_seeds = load_script("candidate_seeds")
    left = tmp_path / "left-repo"
    right = tmp_path / "right-repo"
    left.mkdir()
    right.mkdir()
    (left / "shared.md").write_text("left\n", encoding="utf-8")
    (right / "shared.md").write_text("right\n", encoding="utf-8")

    sources = candidate_seeds.collect_sources([left, right], [])
    labels = [source.label for source in sources]

    assert len(labels) == 2
    assert len(set(labels)) == 2
    assert any("left-repo/shared.md" in label for label in labels)
    assert any("right-repo/shared.md" in label for label in labels)
    by_label = {source.label: source for source in sources}
    assert candidate_seeds.resolve_source("left-repo/shared.md", by_label, [left, right]).root == left
    assert candidate_seeds.resolve_source("right-repo/shared.md", by_label, [left, right]).root == right
    assert candidate_seeds.resolve_source("shared.md", by_label, [left, right]) is None


def test_contract_with_no_known_state_satisfies_state_check(tmp_path):
    contract_index = load_script("contract_index")
    contract_path = tmp_path / "contract-example.md"
    contract_path.write_text(
        """# Stateless Example

- Unique id: contract-example-stateless-abc123
- Name: Stateless Example
- Tags: example

## Purpose

Protects a useful stateless behavior for downstream agents.

## Actors

- Calling client: Invokes the behavior.

## Inputs

- A local request from the Calling client.

## Output

- A deterministic response for the request.

## Internal State

- None known

## Invariants

- None known

## Detailed Behavior

1. The Calling client sends the local request.
2. The behavior returns the deterministic response.

## Alternative Paths

- Invalid request: The Calling client receives a failure response.

## Evidence

- `src/example.py:1` - The behavior has no persisted state.

## Validation

- Scenario: Assert the same input returns the same response.
""",
        encoding="utf-8",
    )

    contract = contract_index.parse_contract(contract_path)
    contract_index.score(contract)

    assert contract.checks["state"] is True
