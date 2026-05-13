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


def write_contract(tmp_path: Path, body: str) -> Path:
    contract_path = tmp_path / "contract-example.md"
    contract_path.write_text(body, encoding="utf-8")
    return contract_path


VALID_CONTRACT = """# Stateless Example

- Unique id: contract-example-stateless-abc123
- Name: Stateless Example
- Tags: example

## Purpose

Protects a useful stateless behavior for downstream agents.

## Actors

- Calling client: Invokes the behavior.

## Inputs

- A local request from the Calling client.

## Pre-conditions

- The Calling client has constructed a local request before invoking the behavior.

## Output

- A deterministic response for the request.

## Post-conditions

- The Calling client observes either the deterministic response or a documented failure response.

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
"""


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
    contract_path = write_contract(tmp_path, VALID_CONTRACT)

    contract = contract_index.parse_contract(contract_path)
    contract_index.score(contract)

    assert contract.checks["state"] is True


def test_contract_condition_sections_are_parsed_and_required_for_io_checks(tmp_path):
    contract_index = load_script("contract_index")
    contract_path = write_contract(tmp_path, VALID_CONTRACT)

    contract = contract_index.parse_contract(contract_path)
    contract_index.score(contract)

    assert "Calling client has constructed a local request" in contract.sections["pre_conditions"]
    assert "Calling client observes either" in contract.sections["post_conditions"]
    assert contract.checks["inputs"] is True
    assert contract.checks["output"] is True
    assert contract.checks["determinacy"] is True


def test_condition_sections_feed_overlap_tokens_and_determinacy(tmp_path):
    contract_index = load_script("contract_index")
    contract_path = write_contract(
        tmp_path,
        VALID_CONTRACT.replace(
            "- The Calling client has constructed a local request before invoking the behavior.",
            "- When eligibility marker is available to the Calling client.",
        )
        .replace(
            "- The Calling client observes either the deterministic response or a documented failure response.",
            "- Then completion marker is archived for the Calling client.",
        )
        .replace(
            "2. The behavior returns the deterministic response.",
            "2. The Calling client receives the deterministic response.",
        )
        .replace(
            "- Invalid request: The Calling client receives a failure response.",
            "- Boundary request: The Calling client receives a documented rejection.",
        ),
    )

    contract = contract_index.parse_contract(contract_path)
    contract_index.score(contract)

    tokens = contract_index.token_set(contract)
    assert "eligibility" in tokens
    assert "archived" in tokens
    assert contract.checks["determinacy"] is True


def test_contract_condition_aliases_are_parsed(tmp_path):
    contract_index = load_script("contract_index")
    contract_path = write_contract(
        tmp_path,
        VALID_CONTRACT.replace("## Pre-conditions", "## Assumptions").replace("## Post-conditions", "## Guarantees"),
    )

    contract = contract_index.parse_contract(contract_path)

    assert "Calling client has constructed a local request" in contract.sections["pre_conditions"]
    assert "Calling client observes either" in contract.sections["post_conditions"]


def test_missing_condition_sections_fail_io_checks(tmp_path):
    contract_index = load_script("contract_index")
    contract_path = write_contract(
        tmp_path,
        VALID_CONTRACT.replace(
            """## Pre-conditions

- The Calling client has constructed a local request before invoking the behavior.

""",
            "",
        ).replace(
            """## Post-conditions

- The Calling client observes either the deterministic response or a documented failure response.

""",
            "",
        ),
    )

    contract = contract_index.parse_contract(contract_path)
    contract_index.score(contract)

    assert contract.checks["inputs"] is False
    assert contract.checks["output"] is False


def test_placeholder_condition_sections_fail_io_checks(tmp_path):
    contract_index = load_script("contract_index")
    contract_path = write_contract(
        tmp_path,
        VALID_CONTRACT.replace(
            "- The Calling client has constructed a local request before invoking the behavior.",
            "- <Required assumptions for when this contract applies.>",
        ).replace(
            "- The Calling client observes either the deterministic response or a documented failure response.",
            "- <Required guarantees after the interaction completes.>",
        ),
    )

    contract = contract_index.parse_contract(contract_path)
    contract_index.score(contract)

    assert contract.checks["inputs"] is False
    assert contract.checks["output"] is False


def test_prune_candidates_only_include_scores_below_twenty_percent_of_observed_max(tmp_path):
    contract_index = load_script("contract_index")

    contracts = [
        contract_index.Contract(path=tmp_path / "contract-high.md", unique_id="contract-high", tags=["shared"], score=10),
        contract_index.Contract(path=tmp_path / "contract-strong.md", unique_id="contract-strong", tags=["shared"], score=8),
        contract_index.Contract(path=tmp_path / "contract-good.md", unique_id="contract-good", tags=["shared"], score=7),
        contract_index.Contract(path=tmp_path / "contract-mid.md", unique_id="contract-mid", tags=["shared"], score=6),
        contract_index.Contract(path=tmp_path / "contract-boundary.md", unique_id="contract-boundary", tags=["shared"], score=2),
        contract_index.Contract(path=tmp_path / "contract-weak.md", unique_id="contract-weak", tags=["only-weak"], score=1),
    ]

    candidates = contract_index.prune_candidates(contracts)

    assert [candidate["id"] for candidate in candidates] == ["contract-weak"]
    assert candidates[0]["preserve_as_gap"] is True
    assert candidates[0]["sole_tags"] == ["only-weak"]


def test_skill_definition_mentions_contract_reconciliation_support():
    skill_dir = ROOT / "skills" / "extract-contracts"
    skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8").lower()
    openai_text = (skill_dir / "agents" / "openai.yaml").read_text(encoding="utf-8").lower()

    assert "extract and reconcile" in skill_text
    assert "reconciliation" in skill_text
    assert "reconcile" in openai_text


def test_skill_definition_requires_concurrent_multi_agent_alternative_exploration():
    skill_dir = ROOT / "skills" / "extract-contracts"
    skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8").lower()
    openai_text = (skill_dir / "agents" / "openai.yaml").read_text(encoding="utf-8").lower()

    assert "multiple agents" in skill_text
    assert "concurrently" in skill_text
    assert "alternative" in skill_text
    assert "parallel" in openai_text
