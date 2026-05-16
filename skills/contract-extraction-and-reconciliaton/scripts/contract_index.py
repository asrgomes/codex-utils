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
        help="User-specified maximum refinement iterations. Required when writing loop state unless already present in state.",
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
    parser.add_argument("--write-state", action="store_true", help="Write convergence state.")
    parser.add_argument("--write-index", action="store_true", help="Write INDEX.md into the contracts directory.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json", help="Output format.")
    args = parser.parse_args()

    if args.write_state and not args.state:
        parser.error("--write-state requires --state")

    contracts_dir = Path(args.contracts_dir)
    previous_state = read_state(Path(args.state)) if args.state else {}
    previous_max_iterations = previous_state.get("max_iterations")
    if args.write_state and args.max_iterations is None and previous_max_iterations is None:
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


def load_contracts(contracts_dir: Path) -> list[Contract]:
    if not contracts_dir.exists():
        return []
    contracts = [parse_contract(path) for path in sorted(contracts_dir.glob("*.md")) if path.name not in IGNORED_NAMES]
    contracts.sort(key=lambda item: item.display_id)
    return contracts


def parse_contract(path: Path) -> Contract:
    contract = Contract(path=path)
    current: str | None = None
    section_lines: dict[str, list[str]] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
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
    for left in contracts:
        for right in contracts:
            if left is right:
                continue
            overlap = jaccard(token_sets[left.display_id], token_sets[right.display_id])
            if overlap > 0:
                left.overlaps.append({"contract": right.display_id, "overlap": round(overlap, 3)})
            left.max_overlap = max(left.max_overlap, overlap)
        left.overlaps.sort(key=lambda item: (-item["overlap"], item["contract"]))


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
    return {token for token in TOKEN_RE.findall(joined) if len(token) > 2}


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

    rank_payload = rank_signature_payload(ranked, merge, split, drop)
    rank_signature = stable_hash(rank_payload)
    previous_signature = previous_rank_signature(previous_state)
    rank_changed = previous_signature is not None and previous_signature != rank_signature

    stop_reasons: list[str] = []
    if effective_max_iterations is not None and effective_iteration >= effective_max_iterations:
        stop_reasons.append(f"max_iterations reached ({effective_iteration}/{effective_max_iterations})")

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
        }
    )

    all_replay_seeds = unique_strings(list_value(previous_state.get("replay_seeds")) + iteration_replay_seeds)
    state = {
        "schema_version": 2,
        "iteration": effective_iteration,
        "max_iterations": effective_max_iterations,
        "min_contracts": effective_min_contracts,
        "material_hash": material_hash,
        "replay_seeds": all_replay_seeds,
        "pending_replay_seeds": [],
        "candidate_outcomes": iteration_candidate_outcomes,
        "seed_history": list_value(previous_state.get("seed_history")),
        "rank_history": rank_history,
        "convergence": convergence,
    }

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
            "replay_seeds": iteration_replay_seeds,
            "candidate_outcomes": iteration_candidate_outcomes,
            "fresh_candidate_complete": fresh_candidate_complete,
        },
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
