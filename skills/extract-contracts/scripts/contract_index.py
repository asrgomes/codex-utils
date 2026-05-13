#!/usr/bin/env python3
"""Parse, score, and index extracted contract markdown files."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path


IGNORED_NAMES = {"INDEX.md", "COVERAGE.md"}
SECTIONS = {
    "actors": "actors",
    "purpose": "purpose",
    "inputs": "inputs",
    "input": "inputs",
    "output": "output",
    "outputs": "output",
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
    parser = argparse.ArgumentParser(description="Score and index extracted contract markdown.")
    parser.add_argument("contracts_dir", help="Directory containing contract .md files.")
    parser.add_argument("--coverage", help="Optional COVERAGE.md path included in convergence checks.")
    parser.add_argument("--state", help="Optional state JSON path for convergence tracking.")
    parser.add_argument("--write-state", action="store_true", help="Write convergence state.")
    parser.add_argument("--write-index", action="store_true", help="Write INDEX.md into the contracts directory.")
    parser.add_argument("--format", choices=("json", "markdown"), default="json", help="Output format.")
    args = parser.parse_args()

    contracts_dir = Path(args.contracts_dir)
    contracts = load_contracts(contracts_dir)
    compute_overlaps(contracts)
    for contract in contracts:
        score(contract)

    result = build_result(contracts, args.coverage, args.state)
    if args.write_state and args.state:
        write_state(Path(args.state), result["convergence"])
    if args.write_index:
        write_index(contracts_dir / "INDEX.md", result)

    if args.format == "markdown":
        print(render_index(result), end="")
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


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
            contract.sections.get("output", ""),
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
        "inputs": meaningful(contract.sections.get("inputs", "")) and meaningful(contract.sections.get("actors", "")),
        "actor_behavior": actors_referenced_in_behavior(contract),
        "output": meaningful(contract.sections.get("output", "")),
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
    actors = contract.sections.get("actors", "")
    if not meaningful(output) or not meaningful(behavior):
        return False
    combined = f"{actors}\n{inputs}\n{behavior}\n{alternative_paths}".lower()
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


def build_result(contracts: list[Contract], coverage: str | None, state: str | None) -> dict:
    material_hash = compute_material_hash(contracts, coverage)
    previous = read_state(Path(state)) if state else {}
    stable_rounds = previous.get("stable_rounds", 0) + 1 if previous.get("material_hash") == material_hash else 0
    stop = stable_rounds >= 2
    return {
        "contracts": [contract_summary(contract) for contract in contracts],
        "merge_candidates": merge_candidates(contracts),
        "split_candidates": split_candidates(contracts),
        "prune_candidates": prune_candidates(contracts),
        "convergence": {
            "material_hash": material_hash,
            "previous_hash": previous.get("material_hash"),
            "stable_rounds": stable_rounds,
            "stop": stop,
        },
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


def prune_candidates(contracts: list[Contract]) -> list[dict]:
    if not contracts:
        return []
    count = max(1, math.ceil(len(contracts) * 0.2))
    tag_counts: dict[str, int] = {}
    for contract in contracts:
        for tag in contract.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    ranked = sorted(contracts, key=lambda item: (item.score, item.display_id))
    candidates = []
    for contract in ranked:
        sole_tags = [tag for tag in contract.tags if tag_counts.get(tag, 0) == 1]
        if sole_tags:
            candidates.append({"id": contract.display_id, "score": contract.score, "preserve_as_gap": True, "sole_tags": sole_tags})
        else:
            candidates.append({"id": contract.display_id, "score": contract.score, "preserve_as_gap": False, "sole_tags": []})
        if len(candidates) >= count:
            break
    return candidates


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


def write_state(path: Path, convergence: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(convergence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_index(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_index(result), encoding="utf-8")


def render_index(result: dict) -> str:
    lines = [
        "# Contract Index",
        "",
        "| Score | Contract | Max overlap | Tags |",
        "| ---: | --- | ---: | --- |",
    ]
    for contract in result["contracts"]:
        tags = ", ".join(contract["tags"])
        lines.append(f"| {contract['score']} | `{contract['id']}` | {contract['max_overlap']:.3f} | {tags} |")
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
    lines.extend(["", "## Prune Candidates", ""])
    if result["prune_candidates"]:
        for item in result["prune_candidates"]:
            suffix = " preserve as coverage gap" if item["preserve_as_gap"] else " prune"
            lines.append(f"- `{item['id']}` score {item['score']} -{suffix}")
    else:
        lines.append("- None")
    convergence = result["convergence"]
    lines.extend(
        [
            "",
            "## Convergence",
            "",
            f"- Stable rounds: {convergence['stable_rounds']}",
            f"- Stop: {str(convergence['stop']).lower()}",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
