#!/usr/bin/env python3
"""Parse, score, and index extracted or reconciled contract markdown files."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


IGNORED_NAMES = {"INDEX.md", "COVERAGE.md"}
DROP_THRESHOLD_RATIO = 0.05
SECTIONS = {
    "actors": "actors",
    "purpose": "purpose",
    "inputs": "inputs",
    "input": "inputs",
    "pre-condition": "pre_conditions",
    "pre-conditions": "pre_conditions",
    "pre condition": "pre_conditions",
    "pre conditions": "pre_conditions",
    "precondition": "pre_conditions",
    "preconditions": "pre_conditions",
    "assumption": "pre_conditions",
    "assumptions": "pre_conditions",
    "requires": "pre_conditions",
    "output": "output",
    "outputs": "output",
    "post-condition": "post_conditions",
    "post-conditions": "post_conditions",
    "post condition": "post_conditions",
    "post conditions": "post_conditions",
    "postcondition": "post_conditions",
    "postconditions": "post_conditions",
    "guarantee": "post_conditions",
    "guarantees": "post_conditions",
    "ensures": "post_conditions",
    "internal state": "internal_state",
    "invariants": "invariants",
    "detailed behavior": "behavior",
    "alternative path": "alternative_paths",
    "alternative paths": "alternative_paths",
    "alternatives paths": "alternative_paths",
    "alternate paths": "alternative_paths",
    "evidence": "evidence",
    "validation": "validation",
}
TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]*")
REFERENCE_RE = re.compile(r"`([^`:\n]+)(?::(\d+))?`")
BOUNDARY_ID_RE = re.compile(r"\bboundary-[0-9a-f]{8,}\b")
HASH_RE = re.compile(r"\b[a-f0-9]{64}\b")
COMMON_OVERLAP_TOKENS = {
    "and",
    "are",
    "for",
    "from",
    "has",
    "into",
    "must",
    "not",
    "the",
    "this",
    "that",
    "then",
    "when",
    "with",
}
MAX_OVERLAP_BUCKET = 200
EMPTY_MARKERS = {
    "",
    "none",
    "none known",
    "n/a",
    "tbd",
    "todo",
    "<todo>",
    "<input, assumption, or precondition.>",
    "<input value, actor request, event, or environmental fact supplied to the interaction.>",
    "<observable guarantee, result, side effect, or failure mode.>",
    "<observable result, side effect, or failure mode.>",
    "<required assumptions for when this contract applies.>",
    "<required guarantees after the interaction completes.>",
    "<role name>: <external party and role in this contract.>",
    "<role name>: <external party and role in this contract; reference this role name in behavior text.>",
    "<interaction step naming participating actor role(s).>",
    "<trigger>: <deviation from the primary path and observable outcome.>",
    "<trigger>: <deviation from the primary path, participating actor role(s) when relevant, and observable outcome.>",
}


@dataclass
class Contract:
    path: Path
    raw_text: str = ""
    unique_id: str = ""
    name: str = ""
    tags: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)
    score: int = 0
    checks: dict[str, bool] = field(default_factory=dict)
    actor_behavior_gaps: list[str] = field(default_factory=list)
    max_overlap: float = 0.0
    overlaps: list[dict] = field(default_factory=list)
    covered_boundary_ids: list[str] = field(default_factory=list)

    @property
    def display_id(self) -> str:
        return self.unique_id or self.path.stem


def main() -> int:
    parser = argparse.ArgumentParser(description="Score and index extracted or reconciled contract markdown.")
    parser.add_argument("contracts_dir", help="Directory containing contract .md files.")
    parser.add_argument("--coverage", help="Optional COVERAGE.md path included in convergence checks.")
    parser.add_argument("--state", help="Optional .contract-state.json path for iteration and convergence tracking.")
    parser.add_argument(
        "--max-iterations",
        type=positive_int,
        help="User-specified maximum refinement iterations. Required for iteration stop policy unless already present in state.",
    )
    parser.add_argument(
        "--min-contracts",
        type=positive_int,
        help="User-specified minimum number of contracts to retain before any drop decision is allowed.",
    )
    parser.add_argument(
        "--iteration",
        type=positive_int,
        help="Current iteration number. Defaults to previous state iteration + 1.",
    )
    parser.add_argument(
        "--replay-seed",
        action="append",
        default=[],
        help="Candidate seed used this iteration. May be repeated; pending seeds written by candidate_seeds.py are consumed automatically.",
    )
    parser.add_argument(
        "--candidate-outcome",
        action="append",
        default=[],
        help="Evidence that a sampled candidate was analyzed and triaged. May be repeated.",
    )
    parser.add_argument(
        "--boundary-inventory",
        help="Optional .boundary-inventory.json path for coverage-frontier completion checks. Defaults to contracts/.boundary-inventory.json when present.",
    )
    parser.add_argument(
        "--stop-policy",
        choices=("iteration", "exhaustive", "both"),
        default=None,
        help="iteration stops at max_iterations; exhaustive stops only when frontier coverage and quality gates are complete.",
    )
    parser.add_argument(
        "--coverage-target",
        choices=("production-spec", "active", "all"),
        default=None,
        help="Boundary roles that must be covered for exhaustive completion.",
    )
    parser.add_argument(
        "--completion-min-score",
        type=score_int,
        default=None,
        help="Minimum score each retained contract must reach for exhaustive completion. Defaults to state or 8.",
    )
    parser.add_argument("--write-state", action="store_true", help="Write convergence state.")
    parser.add_argument("--write-index", action="store_true", help="Write INDEX.md into the contracts directory.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json", help="Output format.")
    args = parser.parse_args()

    if args.write_state and not args.state:
        parser.error("--write-state requires --state")

    contracts_dir = Path(args.contracts_dir)
    previous_state = read_state(Path(args.state)) if args.state else {}
    stop_policy = args.stop_policy or previous_state.get("stop_policy") or "iteration"
    previous_max_iterations = previous_state.get("max_iterations")
    if args.write_state and stop_policy in {"iteration", "both"} and args.max_iterations is None and previous_max_iterations is None:
        parser.error("--max-iterations is required when writing loop state for the first time")
    previous_min_contracts = previous_state.get("min_contracts")
    if args.min_contracts is None and previous_min_contracts is None:
        parser.error("--min-contracts is required")

    contracts = load_contracts(contracts_dir)
    compute_overlaps(contracts)
    for contract in contracts:
        score(contract)

    result = build_result(
        contracts,
        coverage=args.coverage,
        previous_state=previous_state,
        max_iterations=args.max_iterations,
        min_contracts=args.min_contracts,
        iteration=args.iteration,
        replay_seeds=args.replay_seed,
        candidate_outcomes=args.candidate_outcome,
        contracts_dir=contracts_dir,
        boundary_inventory=args.boundary_inventory,
        stop_policy=stop_policy,
        coverage_target=args.coverage_target,
        completion_min_score=args.completion_min_score,
    )
    if args.write_state and args.state:
        write_state(Path(args.state), result["state"])
    if args.write_index:
        write_index(contracts_dir / "INDEX.md", result)

    if args.format == "markdown":
        print(render_index(result), end="")
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def positive_int(text: str) -> int:
    value = int(text)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def score_int(text: str) -> int:
    value = int(text)
    if value < 0 or value > 9:
        raise argparse.ArgumentTypeError("must be between 0 and 9")
    return value


def load_contracts(contracts_dir: Path) -> list[Contract]:
    if not contracts_dir.exists():
        return []
    contracts = [parse_contract(path) for path in sorted(contracts_dir.glob("*.md")) if path.name not in IGNORED_NAMES]
    contracts.sort(key=lambda item: item.display_id)
    return contracts


def parse_contract(path: Path) -> Contract:
    raw_text = path.read_text(encoding="utf-8")
    contract = Contract(path=path, raw_text=raw_text)
    current: str | None = None
    section_lines: dict[str, list[str]] = {}
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if line.startswith("# ") and not contract.name:
            contract.name = line[2:].strip()
            continue
        if line.startswith("## "):
            current = SECTIONS.get(line[3:].strip().lower())
            if current is not None:
                section_lines.setdefault(current, [])
            continue
        if current is not None:
            section_lines[current].append(raw_line.rstrip())
            continue
        parse_metadata(contract, line)

    contract.sections = {key: clean_block(lines) for key, lines in section_lines.items()}
    if not contract.name:
        contract.name = contract.sections.get("name", "") or path.stem
    contract.covered_boundary_ids = sorted(set(BOUNDARY_ID_RE.findall(raw_text)))
    return contract


def parse_metadata(contract: Contract, line: str) -> None:
    lowered = line.lower()
    if lowered.startswith("- unique id:"):
        contract.unique_id = line.split(":", 1)[1].strip()
    elif lowered.startswith("- name:"):
        contract.name = line.split(":", 1)[1].strip()
    elif lowered.startswith("- tags:"):
        tag_text = line.split(":", 1)[1]
        contract.tags = [tag.strip() for tag in tag_text.split(",") if tag.strip()]
    elif re.match(r"^-\s+[a-z -]+:\s+", lowered):
        contract.links.append(line[1:].strip())


def clean_block(lines: list[str]) -> str:
    text = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def compute_overlaps(contracts: list[Contract]) -> None:
    token_sets = {contract.display_id: token_set(contract) for contract in contracts}
    by_id = {contract.display_id: contract for contract in contracts}
    inverted: dict[str, list[str]] = {}
    for contract_id, tokens in token_sets.items():
        for token in tokens:
            inverted.setdefault(token, []).append(contract_id)
    candidate_pairs: set[tuple[str, str]] = set()
    for ids in inverted.values():
        if len(ids) > MAX_OVERLAP_BUCKET:
            continue
        ids = sorted(set(ids))
        for left_index, left_id in enumerate(ids):
            for right_id in ids[left_index + 1 :]:
                candidate_pairs.add((left_id, right_id))
    for left_id, right_id in candidate_pairs:
        overlap = jaccard(token_sets[left_id], token_sets[right_id])
        if overlap <= 0:
            continue
        left = by_id[left_id]
        right = by_id[right_id]
        left.overlaps.append({"contract": right_id, "overlap": round(overlap, 3)})
        right.overlaps.append({"contract": left_id, "overlap": round(overlap, 3)})
        left.max_overlap = max(left.max_overlap, overlap)
        right.max_overlap = max(right.max_overlap, overlap)
    for contract in contracts:
        contract.overlaps.sort(key=lambda item: (-item["overlap"], item["contract"]))


def token_set(contract: Contract) -> set[str]:
    joined = "\n".join(
        [
            contract.name,
            " ".join(contract.tags),
            contract.sections.get("purpose", ""),
            contract.sections.get("actors", ""),
            contract.sections.get("inputs", ""),
            contract.sections.get("pre_conditions", ""),
            contract.sections.get("output", ""),
            contract.sections.get("post_conditions", ""),
            contract.sections.get("invariants", ""),
            contract.sections.get("behavior", ""),
            contract.sections.get("alternative_paths", ""),
        ]
    ).lower()
    return {token for token in TOKEN_RE.findall(joined) if len(token) > 2 and token not in COMMON_OVERLAP_TOKENS}


def jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def score(contract: Contract) -> None:
    checks = {
        "low_overlap": contract.max_overlap <= 0.2,
        "evidence": meaningful(contract.sections.get("evidence", "")) and ":" in contract.sections.get("evidence", ""),
        "inputs": (
            meaningful(contract.sections.get("inputs", ""))
            and meaningful(contract.sections.get("pre_conditions", ""))
            and meaningful(contract.sections.get("actors", ""))
        ),
        "actor_behavior": actors_referenced_in_behavior(contract),
        "output": meaningful(contract.sections.get("output", "")) and meaningful(contract.sections.get("post_conditions", "")),
        "determinacy": deterministic(contract),
        "state": state_clear(contract),
        "value": len(words(contract.sections.get("purpose", ""))) >= 8,
        "testability": testable(contract),
    }
    contract.checks = checks
    contract.score = sum(1 for passed in checks.values() if passed)


def meaningful(text: str) -> bool:
    stripped = normalize_marker(text)
    if stripped in EMPTY_MARKERS:
        return False
    return bool(words(text))


def normalize_marker(text: str) -> str:
    normalized = re.sub(r"^[\s*\-0-9.]+", "", text.strip().lower())
    return normalized.strip()


def words(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def actors_referenced_in_behavior(contract: Contract) -> bool:
    actors = actor_names(contract)
    behavior_text = "\n".join(
        [
            contract.sections.get("behavior", ""),
            contract.sections.get("alternative_paths", ""),
        ]
    )
    missing = [actor for actor in actors if not actor_mentioned(actor, behavior_text)]
    contract.actor_behavior_gaps = missing
    return bool(actors) and meaningful(behavior_text) and not missing


def actor_names(contract: Contract) -> list[str]:
    actors: list[str] = []
    seen: set[str] = set()
    for raw_line in contract.sections.get("actors", "").splitlines():
        line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", raw_line.strip())
        if not line or ":" not in line:
            continue
        name = line.split(":", 1)[0].strip("`*_ ")
        marker = normalize_marker(name)
        if not name or marker in EMPTY_MARKERS or name.startswith("<"):
            continue
        canonical = canonical_phrase(name)
        if canonical and canonical not in seen:
            seen.add(canonical)
            actors.append(name)
    return actors


def actor_mentioned(actor: str, text: str) -> bool:
    actor_phrase = canonical_phrase(actor)
    text_phrase = canonical_phrase(text)
    if not actor_phrase or not text_phrase:
        return False
    return f" {actor_phrase} " in f" {text_phrase} "


def canonical_phrase(text: str) -> str:
    return " ".join(TOKEN_RE.findall(text.lower()))


def deterministic(contract: Contract) -> bool:
    output = contract.sections.get("output", "")
    behavior = contract.sections.get("behavior", "")
    alternative_paths = contract.sections.get("alternative_paths", "")
    inputs = contract.sections.get("inputs", "")
    pre_conditions = contract.sections.get("pre_conditions", "")
    post_conditions = contract.sections.get("post_conditions", "")
    actors = contract.sections.get("actors", "")
    if not meaningful(output) or not meaningful(behavior):
        return False
    combined = f"{actors}\n{inputs}\n{pre_conditions}\n{behavior}\n{alternative_paths}\n{output}\n{post_conditions}".lower()
    return any(word in combined for word in ("when", "then", "return", "produce", "emit", "throw", "fail", "parse", "write", "read"))


def state_clear(contract: Contract) -> bool:
    state = contract.sections.get("internal_state", "")
    invariants = contract.sections.get("invariants", "")
    if meaningful(state) and meaningful(invariants):
        return True
    state_text = normalize_marker(state)
    if state_text == "none known":
        return True
    return "stateless" in [tag.lower() for tag in contract.tags]


def testable(contract: Contract) -> bool:
    validation = contract.sections.get("validation", "").lower()
    invariants = contract.sections.get("invariants", "").lower()
    behavior = contract.sections.get("behavior", "").lower()
    alternative_paths = contract.sections.get("alternative_paths", "").lower()
    joined = "\n".join([validation, invariants, behavior, alternative_paths])
    return any(word in joined for word in ("scenario", "negative", "oracle", "test", "assert", "invariant", "mutation", "runtime"))


def build_result(
    contracts: list[Contract],
    *,
    coverage: str | None,
    previous_state: dict,
    max_iterations: int | None,
    min_contracts: int | None,
    iteration: int | None,
    replay_seeds: list[str],
    candidate_outcomes: list[str],
    contracts_dir: Path,
    boundary_inventory: str | None,
    stop_policy: str,
    coverage_target: str | None,
    completion_min_score: int | None,
) -> dict:
    material_hash = compute_material_hash(contracts, coverage)
    merge = merge_candidates(contracts)
    split = split_candidates(contracts)
    previous_min_contracts = previous_state.get("min_contracts")
    if min_contracts is not None:
        effective_min_contracts = min_contracts
    elif previous_min_contracts is None:
        effective_min_contracts = 0
    else:
        effective_min_contracts = int(previous_min_contracts)
    drop = drop_candidates(contracts, effective_min_contracts)
    ranked = ranked_contracts(contracts)
    effective_coverage_target = str(coverage_target or previous_state.get("coverage_target") or "production-spec")
    previous_completion_min_score = previous_state.get("completion_min_score")
    effective_completion_min_score = (
        completion_min_score
        if completion_min_score is not None
        else int(previous_completion_min_score)
        if previous_completion_min_score is not None
        else 8
    )
    frontier = build_coverage_frontier(
        contracts,
        coverage=coverage,
        contracts_dir=contracts_dir,
        boundary_inventory=boundary_inventory,
        coverage_target=effective_coverage_target,
        completion_min_score=effective_completion_min_score,
        merge=merge,
        split=split,
        drop=drop,
    )

    effective_iteration = iteration or int(previous_state.get("iteration", 0)) + 1
    previous_max_iterations = previous_state.get("max_iterations")
    if max_iterations is not None:
        effective_max_iterations = max_iterations
    elif previous_max_iterations is None:
        effective_max_iterations = None
    else:
        effective_max_iterations = int(previous_max_iterations)
    pending_replay_seeds = [str(seed) for seed in list_value(previous_state.get("pending_replay_seeds")) if str(seed)]
    iteration_replay_seeds = unique_strings(pending_replay_seeds + [str(seed) for seed in replay_seeds if str(seed)])
    iteration_candidate_outcomes = unique_strings([str(outcome) for outcome in candidate_outcomes if str(outcome)])
    fresh_candidate_complete = bool(iteration_replay_seeds) and bool(iteration_candidate_outcomes)

    rank_payload = rank_signature_payload(ranked, merge, split, drop, frontier)
    rank_signature = stable_hash(rank_payload)
    previous_signature = previous_rank_signature(previous_state)
    rank_changed = previous_signature is not None and previous_signature != rank_signature

    stop_reasons: list[str] = []
    if stop_policy in {"iteration", "both"} and effective_max_iterations is not None and effective_iteration >= effective_max_iterations:
        stop_reasons.append(f"max_iterations reached ({effective_iteration}/{effective_max_iterations})")
    if stop_policy in {"exhaustive", "both"} and frontier.get("complete"):
        stop_reasons.append("exhaustive coverage frontier complete")

    convergence = {
        "rank_signature": rank_signature,
        "previous_rank_signature": previous_signature,
        "rank_changed": rank_changed,
        "stop": bool(stop_reasons),
        "stop_reasons": stop_reasons,
    }

    rank_history = list_value(previous_state.get("rank_history"))
    rank_history.append(
        {
            "iteration": effective_iteration,
            "rank_signature": rank_signature,
            "ranked_contracts": ranked,
            "merge_candidates": merge,
            "split_candidates": split,
            "drop_candidates": drop,
            "replay_seeds": iteration_replay_seeds,
            "candidate_outcomes": iteration_candidate_outcomes,
            "fresh_candidate_complete": fresh_candidate_complete,
            "coverage_frontier": frontier,
        }
    )

    all_replay_seeds = unique_strings(list_value(previous_state.get("replay_seeds")) + iteration_replay_seeds)
    frontier_history = list_value(previous_state.get("frontier_history"))
    frontier_history.append({"iteration": effective_iteration, "coverage_frontier": frontier})
    state = dict(previous_state)
    state.update(
        {
        "schema_version": 3,
        "iteration": effective_iteration,
        "max_iterations": effective_max_iterations,
        "min_contracts": effective_min_contracts,
        "stop_policy": stop_policy,
        "coverage_target": effective_coverage_target,
        "completion_min_score": effective_completion_min_score,
        "material_hash": material_hash,
        "replay_seeds": all_replay_seeds,
        "pending_replay_seeds": [],
        "candidate_outcomes": iteration_candidate_outcomes,
        "seed_history": list_value(previous_state.get("seed_history")),
        "rank_history": rank_history,
        "frontier": frontier,
        "frontier_history": frontier_history,
        "convergence": convergence,
        }
    )

    return {
        "contracts": [contract_summary(contract) for contract in contracts],
        "ranked_contracts": ranked,
        "merge_candidates": merge,
        "split_candidates": split,
        "drop_candidates": drop,
        "prune_candidates": drop,
        "drop_threshold": drop_threshold_summary(contracts, effective_min_contracts),
        "iteration": {
            "iteration": effective_iteration,
            "max_iterations": effective_max_iterations,
            "min_contracts": effective_min_contracts,
            "stop_policy": stop_policy,
            "coverage_target": effective_coverage_target,
            "completion_min_score": effective_completion_min_score,
            "replay_seeds": iteration_replay_seeds,
            "candidate_outcomes": iteration_candidate_outcomes,
            "fresh_candidate_complete": fresh_candidate_complete,
        },
        "coverage_frontier": frontier,
        "convergence": convergence,
        "state": state,
    }


def contract_summary(contract: Contract) -> dict:
    return {
        "id": contract.display_id,
        "path": contract.path.as_posix(),
        "name": contract.name,
        "score": contract.score,
        "checks": contract.checks,
        "actor_behavior_gaps": contract.actor_behavior_gaps,
        "max_overlap": round(contract.max_overlap, 3),
        "tags": contract.tags,
        "links": contract.links,
        "covered_boundary_ids": contract.covered_boundary_ids,
        "top_overlaps": contract.overlaps[:3],
    }


def ranked_contracts(contracts: list[Contract]) -> list[dict]:
    ranked = sorted(contracts, key=lambda item: (-item.score, item.max_overlap, item.display_id))
    rows = []
    for index, contract in enumerate(ranked, start=1):
        failed_checks = sorted(check for check, passed in contract.checks.items() if not passed)
        rows.append(
            {
                "rank": index,
                "id": contract.display_id,
                "score": contract.score,
                "max_overlap": round(contract.max_overlap, 3),
                "failed_checks": failed_checks,
                "actor_behavior_gaps": contract.actor_behavior_gaps,
                "links": sorted(contract.links),
            }
        )
    return rows


def merge_candidates(contracts: list[Contract]) -> list[dict]:
    candidates = []
    seen: set[tuple[str, str]] = set()
    for contract in contracts:
        for item in contract.overlaps:
            if item["overlap"] <= 0.2:
                continue
            pair = tuple(sorted([contract.display_id, item["contract"]]))
            if pair in seen:
                continue
            seen.add(pair)
            candidates.append({"left": pair[0], "right": pair[1], "overlap": item["overlap"]})
    return sorted(candidates, key=lambda item: (-item["overlap"], item["left"], item["right"]))


def split_candidates(contracts: list[Contract]) -> list[dict]:
    candidates = []
    for contract in contracts:
        steps = len(
            re.findall(
                r"(?m)^\s*(?:[-*]|\d+\.)\s+",
                "\n".join(
                    [
                        contract.sections.get("behavior", ""),
                        contract.sections.get("alternative_paths", ""),
                    ]
                ),
            )
        )
        if steps > 9:
            candidates.append({"id": contract.display_id, "reason": f"{steps} primary/alternative behavior steps"})
    return candidates


def drop_candidates(contracts: list[Contract], min_contracts: int = 0) -> list[dict]:
    if not contracts:
        return []
    drop_budget = max(0, len(contracts) - min_contracts)
    if drop_budget == 0:
        return []
    max_score = max(contract.score for contract in contracts)
    threshold = max_score * DROP_THRESHOLD_RATIO
    tag_counts: dict[str, int] = {}
    for contract in contracts:
        for tag in contract.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    ranked = sorted(contracts, key=lambda item: (item.score, -item.max_overlap, item.display_id))
    candidates = []
    for contract in ranked:
        if len(candidates) >= drop_budget:
            break
        if contract.score >= threshold:
            continue
        sole_tags = [tag for tag in contract.tags if tag_counts.get(tag, 0) == 1]
        item = {
            "id": contract.display_id,
            "score": contract.score,
            "top_score": max_score,
            "threshold": round(threshold, 3),
            "preserve_as_gap": bool(sole_tags),
            "sole_tags": sole_tags,
        }
        if sole_tags:
            candidates.append(item)
        else:
            candidates.append(item)
    return candidates


def prune_candidates(contracts: list[Contract], min_contracts: int = 0) -> list[dict]:
    """Backward-compatible alias for older callers; the workflow now calls these drops."""
    return drop_candidates(contracts, min_contracts)


def drop_threshold_summary(contracts: list[Contract], min_contracts: int) -> dict:
    top_score = max((contract.score for contract in contracts), default=0)
    return {
        "ratio": DROP_THRESHOLD_RATIO,
        "top_score": top_score,
        "threshold": round(top_score * DROP_THRESHOLD_RATIO, 3),
        "min_contracts": min_contracts,
        "drop_budget": max(0, len(contracts) - min_contracts),
    }


def rank_signature_payload(
    ranked: list[dict],
    merge: list[dict],
    split: list[dict],
    drop: list[dict],
    frontier: dict | None = None,
) -> dict:
    return {
        "ranked_contracts": [
            {
                "rank": item["rank"],
                "id": item["id"],
                "score": item["score"],
                "max_overlap": item["max_overlap"],
                "failed_checks": item["failed_checks"],
                "actor_behavior_gaps": item["actor_behavior_gaps"],
                "links": item["links"],
            }
            for item in ranked
        ],
        "merge_candidates": merge,
        "split_candidates": split,
        "drop_candidates": drop,
        "coverage_frontier": {
            "blockers": (frontier or {}).get("blockers", {}),
            "active_required_boundaries": (frontier or {}).get("active_required_boundaries", 0),
            "covered_required_boundaries": (frontier or {}).get("covered_required_boundaries", 0),
            "referenced_stale_boundaries": (frontier or {}).get("referenced_stale_boundaries", 0),
            "complete": (frontier or {}).get("complete", False),
        },
    }


def stable_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def previous_rank_signature(previous: dict) -> str | None:
    history = previous.get("rank_history", [])
    if isinstance(history, list) and history:
        last = history[-1]
        if isinstance(last, dict):
            signature = last.get("rank_signature")
            if isinstance(signature, str):
                return signature
    convergence = previous.get("convergence", {})
    if isinstance(convergence, dict):
        signature = convergence.get("rank_signature")
        if isinstance(signature, str):
            return signature
    signature = previous.get("rank_signature")
    return signature if isinstance(signature, str) else None


def unique_strings(values: list) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def list_value(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def compute_material_hash(contracts: list[Contract], coverage: str | None) -> str:
    payload = {
        "contracts": [
            {
                "id": contract.display_id,
                "name": contract.name,
                "tags": contract.tags,
                "links": contract.links,
                "sections": contract.sections,
                "score": contract.score,
            }
            for contract in contracts
        ],
        "coverage": Path(coverage).read_text(encoding="utf-8") if coverage and Path(coverage).exists() else "",
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_coverage_frontier(
    contracts: list[Contract],
    *,
    coverage: str | None,
    contracts_dir: Path,
    boundary_inventory: str | None,
    coverage_target: str,
    completion_min_score: int,
    merge: list[dict],
    split: list[dict],
    drop: list[dict],
) -> dict:
    inventory_path = resolve_boundary_inventory(boundary_inventory, contracts_dir)
    inventory = read_json(inventory_path) if inventory_path else {}
    boundaries = inventory.get("boundaries", []) if isinstance(inventory, dict) else []
    contract_coverage = collect_contract_coverage(contracts)

    required = []
    covered_required = []
    uncovered_required = []
    stale_boundaries = []
    referenced_stale_boundaries = []
    by_kind: dict[str, int] = {}
    by_role: dict[str, int] = {}
    by_status: dict[str, int] = {}
    samples = {"uncovered_required": [], "referenced_stale": [], "covered_required": []}

    for boundary in boundaries:
        if not isinstance(boundary, dict):
            continue
        status = str(boundary.get("status", "active"))
        role = str(boundary.get("evidence_role", ""))
        by_role[role] = by_role.get(role, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        covered_by = covered_by_contracts(boundary, contract_coverage, allow_path_line=status == "active")
        item = frontier_boundary_summary(boundary, covered_by)
        if status != "active":
            stale_boundaries.append(item)
            if covered_by:
                referenced_stale_boundaries.append(item)
                append_sample(samples["referenced_stale"], item)
            by_kind["referenced_stale" if covered_by else "stale_unreferenced"] = (
                by_kind.get("referenced_stale" if covered_by else "stale_unreferenced", 0) + 1
            )
            continue
        if required_for_completion(boundary, coverage_target):
            required.append(item)
            if covered_by:
                covered_required.append(item)
                append_sample(samples["covered_required"], item)
                by_kind["covered_required"] = by_kind.get("covered_required", 0) + 1
            else:
                uncovered_required.append(item)
                append_sample(samples["uncovered_required"], item)
                by_kind["uncovered_required"] = by_kind.get("uncovered_required", 0) + 1
        elif covered_by:
            by_kind["covered_optional"] = by_kind.get("covered_optional", 0) + 1
        else:
            by_kind["uncovered_optional"] = by_kind.get("uncovered_optional", 0) + 1

    below_min_score = [
        {"id": contract.display_id, "score": contract.score}
        for contract in contracts
        if contract.score < completion_min_score
    ]
    actor_behavior_gaps = [
        {"id": contract.display_id, "actors": contract.actor_behavior_gaps}
        for contract in contracts
        if contract.actor_behavior_gaps
    ]
    unresolved_gaps = unresolved_coverage_gaps(coverage)
    blockers = {
        "uncovered_required_boundaries": len(uncovered_required),
        "referenced_stale_boundaries": len(referenced_stale_boundaries),
        "contracts_below_min_score": len(below_min_score),
        "actor_behavior_gaps": len(actor_behavior_gaps),
        "merge_candidates": len(merge),
        "split_candidates": len(split),
        "drop_candidates": len(drop),
        "unresolved_coverage_gaps": len(unresolved_gaps),
    }
    frontier_available = bool(inventory_path and inventory_path.exists())
    complete = frontier_available and all(value == 0 for value in blockers.values())
    return {
        "frontier_available": frontier_available,
        "inventory_path": inventory_path.as_posix() if inventory_path else "",
        "inventory_hash": inventory.get("inventory_hash") if isinstance(inventory, dict) else None,
        "coverage_target": coverage_target,
        "completion_min_score": completion_min_score,
        "active_required_boundaries": len(required),
        "covered_required_boundaries": len(covered_required),
        "uncovered_required_boundaries": len(uncovered_required),
        "stale_boundaries": len(stale_boundaries),
        "referenced_stale_boundaries": len(referenced_stale_boundaries),
        "boundary_counts_by_role": by_role,
        "boundary_counts_by_status": by_status,
        "frontier_counts_by_kind": by_kind,
        "quality_frontier": {
            "contracts_below_min_score": below_min_score,
            "actor_behavior_gaps": actor_behavior_gaps,
            "merge_candidates": merge,
            "split_candidates": split,
            "drop_candidates": drop,
            "unresolved_coverage_gaps": unresolved_gaps,
        },
        "blockers": blockers,
        "samples": samples,
        "complete": complete,
    }


def resolve_boundary_inventory(boundary_inventory: str | None, contracts_dir: Path) -> Path | None:
    if boundary_inventory:
        return Path(boundary_inventory)
    candidate = contracts_dir / ".boundary-inventory.json"
    return candidate if candidate.exists() else None


def collect_contract_coverage(contracts: list[Contract]) -> list[dict]:
    coverages: list[dict] = []
    for contract in contracts:
        refs = []
        for ref_text, line_text in REFERENCE_RE.findall(contract.raw_text):
            line = int(line_text) if line_text else None
            refs.append({"path": ref_text.strip(), "line": line})
        coverages.append(
            {
                "contract": contract.display_id,
                "boundary_ids": set(BOUNDARY_ID_RE.findall(contract.raw_text)),
                "hashes": set(HASH_RE.findall(contract.raw_text.lower())),
                "refs": refs,
            }
        )
    return coverages


def covered_by_contracts(boundary: dict, contract_coverage: list[dict], *, allow_path_line: bool = True) -> list[str]:
    boundary_id = str(boundary.get("boundary_id", ""))
    snippet_hash = str(boundary.get("snippet_hash", ""))
    boundary_paths = {
        str(boundary.get("path", "")),
        str(boundary.get("repo_relative_path", "")),
        label_without_root(str(boundary.get("path", ""))),
    }
    boundary_paths = {path for path in boundary_paths if path}
    line_range = boundary.get("line_range", [1, 1])
    try:
        start_line = int(line_range[0])
        end_line = int(line_range[1])
    except (TypeError, ValueError, IndexError):
        start_line, end_line = 1, 1
    covered: list[str] = []
    for item in contract_coverage:
        if boundary_id and boundary_id in item.get("boundary_ids", set()):
            covered.append(str(item["contract"]))
            continue
        if snippet_hash and snippet_hash in item.get("hashes", set()):
            covered.append(str(item["contract"]))
            continue
        if not allow_path_line:
            continue
        for ref in item.get("refs", []):
            ref_path = str(ref.get("path", ""))
            if not path_matches(ref_path, boundary_paths):
                continue
            ref_line = ref.get("line")
            if ref_line is None or lines_overlap(int(ref_line), int(ref_line), start_line, end_line, tolerance=3):
                covered.append(str(item["contract"]))
                break
    return unique_strings(covered)


def required_for_completion(boundary: dict, coverage_target: str) -> bool:
    if coverage_target == "all":
        return boundary.get("status", "active") == "active"
    if boundary.get("status", "active") != "active":
        return False
    if coverage_target == "active":
        return True
    return boundary.get("evidence_role") in {"production_anchor", "spec_anchor"}


def frontier_boundary_summary(boundary: dict, covered_by: list[str]) -> dict:
    return {
        "boundary_id": boundary.get("boundary_id", ""),
        "boundary_type": boundary.get("boundary_type", ""),
        "path": boundary.get("path", ""),
        "repo_relative_path": boundary.get("repo_relative_path", ""),
        "line_range": boundary.get("line_range", []),
        "symbol": boundary.get("symbol", ""),
        "evidence_role": boundary.get("evidence_role", ""),
        "status": boundary.get("status", "active"),
        "stale_reason": boundary.get("stale_reason", ""),
        "covered_by": covered_by,
    }


def append_sample(items: list[dict], item: dict, limit: int = 20) -> None:
    if len(items) < limit:
        items.append(item)


def unresolved_coverage_gaps(coverage: str | None) -> list[dict]:
    if not coverage:
        return []
    path = Path(coverage)
    if not path.exists():
        return []
    gaps: list[dict] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        stripped = raw_line.strip()
        lowered = stripped.lower()
        if not stripped or stripped.startswith("#") or "[x]" in lowered:
            continue
        checklist_gap = "[ ]" in lowered
        bullet_gap = bool(re.match(r"^[-*]\s+(gap|missing|uncovered|unknown|todo)\b", lowered))
        todo_gap = "todo" in lowered or "fixme" in lowered
        if checklist_gap or bullet_gap or todo_gap:
            gaps.append({"line": line_number, "text": stripped[:240]})
    return gaps


def path_matches(ref_path: str, candidates: set[str]) -> bool:
    normalized = ref_path.strip()
    if normalized in candidates:
        return True
    normalized_tail = label_without_root(normalized)
    if normalized_tail in candidates:
        return True
    return any(candidate.endswith("/" + normalized) or normalized.endswith("/" + candidate) for candidate in candidates)


def label_without_root(label: str) -> str:
    parts = label.split("/", 1)
    return parts[1] if len(parts) == 2 else label


def lines_overlap(left_start: int, left_end: int, right_start: int, right_end: int, *, tolerance: int = 0) -> bool:
    return left_start <= right_end + tolerance and right_start <= left_end + tolerance


def read_json(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def read_state(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_index(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_index(result), encoding="utf-8")


def render_index(result: dict) -> str:
    lines = [
        "# Contract Index",
        "",
        "| Rank | Score | Contract | Max overlap | Tags |",
        "| ---: | ---: | --- | ---: | --- |",
    ]
    contracts_by_id = {contract["id"]: contract for contract in result["contracts"]}
    for ranked in result["ranked_contracts"]:
        contract = contracts_by_id[ranked["id"]]
        tags = ", ".join(contract["tags"])
        lines.append(
            f"| {ranked['rank']} | {contract['score']} | `{contract['id']}` | {contract['max_overlap']:.3f} | {tags} |"
        )
    lines.extend(["", "## Merge Candidates", ""])
    if result["merge_candidates"]:
        for item in result["merge_candidates"]:
            lines.append(f"- `{item['left']}` + `{item['right']}` overlap {item['overlap']:.3f}")
    else:
        lines.append("- None")
    lines.extend(["", "## Split Candidates", ""])
    if result["split_candidates"]:
        for item in result["split_candidates"]:
            lines.append(f"- `{item['id']}` - {item['reason']}")
    else:
        lines.append("- None")
    lines.extend(["", "## Actor-Behavior Gaps", ""])
    gap_contracts = [contract for contract in result["contracts"] if contract["actor_behavior_gaps"]]
    if gap_contracts:
        for contract in gap_contracts:
            actors = ", ".join(f"`{actor}`" for actor in contract["actor_behavior_gaps"])
            lines.append(f"- `{contract['id']}` missing behavior references for actor(s): {actors}")
    else:
        lines.append("- None")
    threshold = result["drop_threshold"]
    lines.extend(
        [
            "",
            "## Drop Candidates",
            "",
            f"- Threshold: score below {threshold['threshold']:.3f} "
            f"({threshold['ratio']:.0%} of top score {threshold['top_score']})",
            f"- Minimum retained contracts: {threshold['min_contracts']}",
            f"- Drop budget: {threshold['drop_budget']}",
        ]
    )
    if result["drop_candidates"]:
        for item in result["drop_candidates"]:
            suffix = " preserve as coverage gap" if item["preserve_as_gap"] else " drop"
            lines.append(f"- `{item['id']}` score {item['score']} -{suffix}")
    else:
        lines.append("- None")
    frontier = result.get("coverage_frontier", {})
    lines.extend(
        [
            "",
            "## Coverage Frontier",
            "",
            f"- Inventory available: {str(frontier.get('frontier_available', False)).lower()}",
            f"- Coverage target: {frontier.get('coverage_target', '')}",
            f"- Completion minimum score: {frontier.get('completion_min_score', '')}",
            f"- Required active boundaries: {frontier.get('covered_required_boundaries', 0)} / "
            f"{frontier.get('active_required_boundaries', 0)} covered",
            f"- Uncovered required boundaries: {frontier.get('uncovered_required_boundaries', 0)}",
            f"- Referenced stale boundaries: {frontier.get('referenced_stale_boundaries', 0)}",
            f"- Complete: {str(frontier.get('complete', False)).lower()}",
        ]
    )
    blockers = frontier.get("blockers", {}) if isinstance(frontier.get("blockers", {}), dict) else {}
    if blockers:
        lines.append("- Blockers: " + ", ".join(f"{key}={value}" for key, value in sorted(blockers.items())))
    samples = frontier.get("samples", {}) if isinstance(frontier.get("samples", {}), dict) else {}
    uncovered_samples = samples.get("uncovered_required", []) if isinstance(samples.get("uncovered_required", []), list) else []
    if uncovered_samples:
        lines.extend(["", "### Sample Uncovered Required Boundaries", ""])
        for item in uncovered_samples[:10]:
            lines.append(
                f"- `{item.get('boundary_id', '')}` {item.get('boundary_type', '')} "
                f"`{item.get('path', '')}` lines {item.get('line_range', [])}"
            )
    stale_samples = samples.get("referenced_stale", []) if isinstance(samples.get("referenced_stale", []), list) else []
    if stale_samples:
        lines.extend(["", "### Sample Referenced Stale Boundaries", ""])
        for item in stale_samples[:10]:
            lines.append(
                f"- `{item.get('boundary_id', '')}` `{item.get('path', '')}` "
                f"covered by {', '.join(item.get('covered_by', []))}: {item.get('stale_reason', '')}"
            )
    iteration = result["iteration"]
    convergence = result["convergence"]
    stop_reasons = convergence["stop_reasons"] or ["not reached"]
    lines.extend(
        [
            "",
            "## Convergence",
            "",
            f"- Iteration: {iteration['iteration']}"
            + (f" / {iteration['max_iterations']}" if iteration["max_iterations"] is not None else ""),
            f"- Minimum retained contracts: {iteration['min_contracts']}",
            f"- Stop policy: {iteration['stop_policy']}",
            f"- Coverage target: {iteration['coverage_target']}",
            f"- Fresh candidates complete: {str(iteration['fresh_candidate_complete']).lower()}",
            f"- Stop: {str(convergence['stop']).lower()}",
            f"- Stop reason: {'; '.join(stop_reasons)}",
        ]
    )
    if iteration["replay_seeds"]:
        lines.extend(["", "## Replay Seeds", ""])
        for seed in iteration["replay_seeds"]:
            lines.append(f"- `{seed}`")
    if iteration["candidate_outcomes"]:
        lines.extend(["", "## Candidate Outcomes", ""])
        for outcome in iteration["candidate_outcomes"]:
            lines.append(f"- {outcome}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
