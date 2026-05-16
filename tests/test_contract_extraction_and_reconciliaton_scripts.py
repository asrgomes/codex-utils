from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "contract-extraction-and-reconciliaton"
SCRIPTS = SKILL_DIR / "scripts"


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


def write_file(root: Path, rel: str, body: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


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


def test_prune_candidates_only_include_scores_below_five_percent_of_observed_max(tmp_path):
    contract_index = load_script("contract_index")

    contracts = [
        contract_index.Contract(path=tmp_path / "contract-high.md", unique_id="contract-high", tags=["shared"], score=9),
        contract_index.Contract(path=tmp_path / "contract-strong.md", unique_id="contract-strong", tags=["shared"], score=8),
        contract_index.Contract(path=tmp_path / "contract-good.md", unique_id="contract-good", tags=["shared"], score=7),
        contract_index.Contract(path=tmp_path / "contract-mid.md", unique_id="contract-mid", tags=["shared"], score=6),
        contract_index.Contract(path=tmp_path / "contract-boundary.md", unique_id="contract-boundary", tags=["shared"], score=1),
        contract_index.Contract(path=tmp_path / "contract-weak.md", unique_id="contract-weak", tags=["only-weak"], score=0),
    ]

    candidates = contract_index.prune_candidates(contracts, min_contracts=1)

    assert [candidate["id"] for candidate in candidates] == ["contract-weak"]
    assert candidates[0]["preserve_as_gap"] is True
    assert candidates[0]["sole_tags"] == ["only-weak"]


def test_five_percent_drop_threshold_only_drops_zero_score_on_real_score_scale(tmp_path):
    contract_index = load_script("contract_index")

    contracts = [
        contract_index.Contract(path=tmp_path / "contract-high.md", unique_id="contract-high", tags=["shared"], score=9),
        contract_index.Contract(path=tmp_path / "contract-one.md", unique_id="contract-one", tags=["shared"], score=1),
    ]

    assert contract_index.prune_candidates(contracts, min_contracts=1) == []


def test_prune_candidates_respects_minimum_retained_contract_count(tmp_path):
    contract_index = load_script("contract_index")

    contracts = [
        contract_index.Contract(path=tmp_path / "contract-high.md", unique_id="contract-high", tags=["shared"], score=10),
        contract_index.Contract(path=tmp_path / "contract-weak-a.md", unique_id="contract-weak-a", tags=["shared"], score=0),
        contract_index.Contract(path=tmp_path / "contract-weak-b.md", unique_id="contract-weak-b", tags=["shared"], score=0),
    ]

    assert contract_index.prune_candidates(contracts, min_contracts=3) == []
    candidates = contract_index.prune_candidates(contracts, min_contracts=2)

    assert [candidate["id"] for candidate in candidates] == ["contract-weak-a"]


def test_candidate_seeds_include_gap_ref_when_coverage_has_gap(tmp_path):
    candidate_seeds = load_script("candidate_seeds")
    repo = tmp_path / "repo"
    contracts = tmp_path / "contracts"
    repo.mkdir()
    contracts.mkdir()
    (repo / "source.py").write_text("print('source')\n", encoding="utf-8")
    (contracts / "COVERAGE.md").write_text("## Missing\n- gap: source behavior is uncovered\n", encoding="utf-8")

    breadth_sources = candidate_seeds.collect_sources([repo], [])
    depth_refs = candidate_seeds.collect_depth_refs(contracts, breadth_sources, [repo])
    seeds = candidate_seeds.select_seeds(candidate_seeds.random.Random("fixed"), breadth_sources, depth_refs, 2, 10)

    assert any(seed["path"] == "COVERAGE.md" and "known coverage gap" in seed["reason"] for seed in seeds)


def test_boundary_inventory_profiles_projects_and_classifies_evidence_roles(tmp_path):
    boundary_inventory = load_script("boundary_inventory")
    repo = tmp_path / "repo"
    contracts = tmp_path / "contracts"
    repo.mkdir()
    contracts.mkdir()
    write_file(
        repo,
        "pom.xml",
        "<project><modules><module>api</module><module>worker</module></modules></project>\n",
    )
    write_file(repo, "settings.gradle", "include ':web', ':jobs'\n")
    write_file(repo, "go.mod", "module example.com/acme\n")
    write_file(repo, "pyproject.toml", "[project]\nname = 'acme'\n")
    write_file(repo, "package.json", "{\"workspaces\": [\"packages/*\"]}\n")
    write_file(
        repo,
        "src/main/java/acme/UserController.java",
        "@RestController\nclass UserController {\n  @GetMapping(\"/users\")\n  String users() { return \"ok\"; }\n}\n",
    )
    write_file(
        repo,
        "src/main/java/acme/MockWebhookController.java",
        "@RestController\nclass MockWebhookController {\n  @PostMapping(\"/mock\")\n  String mock() { return \"ok\"; }\n}\n",
    )
    write_file(
        repo,
        "src/test/java/acme/UserControllerTest.java",
        "class UserControllerTest {\n  @Test void routes() { assert true; }\n}\n",
    )
    write_file(
        repo,
        "cmd/server/main.go",
        "package main\nimport \"net/http\"\nfunc main() { http.HandleFunc(\"/health\", func(w http.ResponseWriter, r *http.Request) {}) }\n",
    )
    write_file(
        repo,
        "src/app.py",
        "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/ready')\ndef ready(): return 'ok'\n",
    )
    write_file(repo, "src/routes.ts", "router.post('/submit', handler)\n")

    inventory = boundary_inventory.build_inventory([repo], contracts_dir=contracts, write=True)
    roles = {boundary["repo_relative_path"]: boundary["evidence_role"] for boundary in inventory["boundaries"]}
    boundary_types = {boundary["boundary_type"] for boundary in inventory["boundaries"]}
    profile = inventory["repos"][0]["project_profile"]

    assert {"maven", "gradle", "golang", "python", "typescript"}.issubset(profile["ecosystems"])
    assert profile["structure"]["maven"]["modules"] == ["api", "worker"]
    assert "rest_controller" in boundary_types
    assert roles["src/main/java/acme/UserController.java"] == "production_anchor"
    assert roles["src/main/java/acme/MockWebhookController.java"] == "support_code"
    assert (contracts / ".boundary-inventory.json").exists()


def test_boundary_inventory_reuses_unchanged_boundaries_and_marks_stale(tmp_path):
    boundary_inventory = load_script("boundary_inventory")
    repo = tmp_path / "repo"
    contracts = tmp_path / "contracts"
    repo.mkdir()
    contracts.mkdir()
    source = write_file(
        repo,
        "src/main/java/acme/UserController.java",
        "@RestController\nclass UserController {\n  @GetMapping(\"/users\")\n  String users() { return \"ok\"; }\n}\n",
    )
    inventory_path = contracts / ".boundary-inventory.json"

    first = boundary_inventory.build_inventory([repo], contracts_dir=contracts, existing_path=inventory_path, write=True)
    second = boundary_inventory.build_inventory(
        [repo], contracts_dir=contracts, existing_path=inventory_path, reuse=True, write=True
    )

    assert first["summary"]["by_status"]["active"] >= 1
    assert any(boundary["reused"] is True for boundary in second["boundaries"])

    source.write_text("class UserController { String users() { return \"ok\"; } }\n", encoding="utf-8")
    third = boundary_inventory.build_inventory(
        [repo], contracts_dir=contracts, existing_path=inventory_path, reuse=True, write=False
    )

    assert any(boundary["status"] == "stale" for boundary in third["boundaries"])


def test_candidate_seeds_use_boundary_inventory_before_random_breadth(tmp_path):
    candidate_seeds = load_script("candidate_seeds")
    repo = tmp_path / "repo"
    contracts = tmp_path / "contracts"
    repo.mkdir()
    contracts.mkdir()
    write_file(
        repo,
        "src/app.py",
        "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/ready')\ndef ready(): return 'ok'\n",
    )
    write_file(repo, "plain.py", "VALUE = 1\n")

    sources = candidate_seeds.collect_sources([repo], [])
    boundary_refs = candidate_seeds.collect_boundary_refs(contracts, sources, [repo], write_inventory=True, reuse=True)
    seeds = candidate_seeds.select_seeds(
        candidate_seeds.random.Random("fixed"), sources, [], 2, 10, boundary_refs=boundary_refs
    )

    assert seeds
    assert all(seed["strategy"] == "boundary" for seed in seeds)
    assert all("boundary_id" in seed for seed in seeds)


def test_candidate_seeds_disable_blind_random_breadth_by_default(tmp_path):
    candidate_seeds = load_script("candidate_seeds")
    repo = tmp_path / "repo"
    repo.mkdir()
    write_file(repo, "plain.py", "VALUE = 1\n")

    sources = candidate_seeds.collect_sources([repo], [])
    seeds = candidate_seeds.select_seeds(candidate_seeds.random.Random("fixed"), sources, [], 2, 10)
    random_seeds = candidate_seeds.select_seeds(
        candidate_seeds.random.Random("fixed"), sources, [], 2, 10, random_count=1
    )

    assert seeds == []
    assert [seed["strategy"] for seed in random_seeds] == ["breadth"]


def test_unchanged_rank_does_not_stop_before_max_iterations(tmp_path):
    contract_index = load_script("contract_index")
    contracts = [
        contract_index.Contract(path=tmp_path / "contract-high.md", unique_id="contract-high", tags=["shared"], score=9)
    ]
    first = contract_index.build_result(
        contracts,
        coverage=None,
        previous_state={},
        max_iterations=5,
        min_contracts=1,
        iteration=1,
        replay_seeds=["seed-1"],
        candidate_outcomes=["rejected candidate from seed-1"],
    )
    second = contract_index.build_result(
        contracts,
        coverage=None,
        previous_state=first["state"],
        max_iterations=5,
        min_contracts=1,
        iteration=2,
        replay_seeds=["seed-2"],
        candidate_outcomes=[],
    )

    assert second["convergence"]["rank_changed"] is False
    assert second["convergence"]["stop"] is False


def test_stop_condition_is_max_iterations_only(tmp_path):
    contract_index = load_script("contract_index")
    contracts = [
        contract_index.Contract(path=tmp_path / "contract-high.md", unique_id="contract-high", tags=["shared"], score=9)
    ]
    first = contract_index.build_result(
        contracts,
        coverage=None,
        previous_state={},
        max_iterations=5,
        min_contracts=1,
        iteration=1,
        replay_seeds=["seed-1"],
        candidate_outcomes=["rejected candidate from seed-1"],
    )
    second = contract_index.build_result(
        contracts,
        coverage=None,
        previous_state=first["state"],
        max_iterations=5,
        min_contracts=1,
        iteration=2,
        replay_seeds=["seed-2"],
        candidate_outcomes=["rejected candidate from seed-2"],
    )
    third = contract_index.build_result(
        contracts,
        coverage=None,
        previous_state=second["state"],
        max_iterations=3,
        min_contracts=1,
        iteration=3,
        replay_seeds=["seed-3"],
        candidate_outcomes=["rejected candidate from seed-3"],
    )

    assert third["convergence"]["stop"] is True
    assert third["convergence"]["stop_reasons"] == ["max_iterations reached (3/3)"]


def test_skill_definition_mentions_contract_reconciliation_support():
    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").lower()
    openai_text = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8").lower()

    assert "extract and reconcile" in skill_text
    assert "name: contract-extraction-and-reconciliaton" in skill_text
    assert "reconciliation" in skill_text
    assert "reconcile" in openai_text


def test_skill_definition_requires_concurrent_multi_agent_alternative_exploration():
    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").lower()
    openai_text = (SKILL_DIR / "agents" / "openai.yaml").read_text(encoding="utf-8").lower()

    assert "multiple agents" in skill_text
    assert "concurrently" in skill_text
    assert "alternative" in skill_text
    assert "parallel" in openai_text


def test_skill_definition_requires_codepath_tracing_for_source_location_candidates():
    skill_text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").lower()
    rubric_text = (SKILL_DIR / "references" / "scoring-rubric.md").read_text(encoding="utf-8").lower()

    assert "source-code location" in skill_text
    assert "code paths" in skill_text
    assert "caller" in skill_text
    assert "callee" in skill_text
    assert "caller/callee branches" in rubric_text
