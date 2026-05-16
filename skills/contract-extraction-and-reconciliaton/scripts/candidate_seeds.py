#!/usr/bin/env python3
"""Select boundary-backed code/spec slices for embryonic contract candidates."""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import re
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path


SKIP_PARTS = {".git", "target", "node_modules", ".idea", ".gradle", "build", "dist", "__pycache__"}
TEXT_EXTENSIONS = {
    ".java",
    ".kt",
    ".py",
    ".go",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".md",
    ".txt",
    ".xml",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".properties",
    ".gradle",
    ".sh",
    ".bash",
    ".bats",
    ".sql",
}
REFERENCE_RE = re.compile(r"`([^`:\n]+)(?::(\d+))?`")


def load_boundary_inventory_module():
    try:
        import boundary_inventory  # type: ignore

        return boundary_inventory
    except ModuleNotFoundError:
        path = Path(__file__).with_name("boundary_inventory.py")
        spec = importlib.util.spec_from_file_location("boundary_inventory", path)
        if spec is None or spec.loader is None:
            raise
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


@dataclass(frozen=True)
class SourceFile:
    root: Path
    path: Path
    label: str
    kind: str
    lines: int


@dataclass(frozen=True)
class DepthReference:
    source: SourceFile
    line: int | None
    reason: str


@dataclass(frozen=True)
class BoundaryReference:
    source: SourceFile
    start_line: int
    end_line: int
    boundary: dict


def main() -> int:
    parser = argparse.ArgumentParser(description="Select boundary-backed embryonic contract candidate seeds.")
    parser.add_argument("--repo", action="append", default=[], help="Local repository path. May be repeated.")
    parser.add_argument("--spec", action="append", default=[], help="Local specification file path. May be repeated.")
    parser.add_argument("--contracts", help="Existing contracts directory for boundary inventory and depth-oriented seeds.")
    parser.add_argument("--count", type=int, default=12, help="Number of seeds to emit.")
    parser.add_argument(
        "--random-count",
        type=int,
        default=0,
        help="Number of explicit blind random breadth seeds to add. Defaults to 0 for large-repo efficiency.",
    )
    parser.add_argument("--window", type=int, default=30, help="Maximum line window per seed.")
    parser.add_argument("--seed", help="Replay seed. Omit for a fresh replay token.")
    parser.add_argument("--state", help="Optional .contract-state.json path to record the replay seed.")
    parser.add_argument("--write-state", action="store_true", help="Append the generated replay seed to pending state.")
    parser.add_argument(
        "--refresh-boundaries",
        action="store_true",
        help="Force a fresh boundary inventory instead of reusing unchanged source-anchored entries.",
    )
    args = parser.parse_args()

    if args.write_state and not args.state:
        parser.error("--write-state requires --state")

    replay_seed = args.seed or secrets.token_hex(12)
    rng = random.Random(replay_seed)
    repos = [Path(repo).resolve() for repo in args.repo] or [Path.cwd()]
    specs = [Path(spec).resolve() for spec in args.spec]
    contracts_dir = Path(args.contracts).resolve() if args.contracts else None

    breadth_sources = collect_sources(repos, specs)
    boundary_refs = collect_boundary_refs(
        contracts_dir,
        breadth_sources,
        repos,
        write_inventory=bool(contracts_dir),
        reuse=not args.refresh_boundaries,
    )
    depth_refs = collect_depth_refs(contracts_dir, breadth_sources, repos) if contracts_dir else []
    seeds = select_seeds(
        rng,
        breadth_sources,
        depth_refs,
        max(args.count, 0),
        max(args.window, 1),
        boundary_refs=boundary_refs,
        random_count=max(args.random_count, 0),
    )
    payload = {
        "seed": replay_seed,
        "requested_count": max(args.count, 0),
        "count": len(seeds),
        "boundary_available": bool(boundary_refs),
        "depth_available": bool(depth_refs),
        "random_count": max(args.random_count, 0),
        "seeds": seeds,
    }
    if args.write_state and args.state:
        record_pending_seed(Path(args.state), replay_seed, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def record_pending_seed(state_path: Path, replay_seed: str, payload: dict) -> None:
    state = read_state(state_path)
    pending = unique_strings(list_value(state.get("pending_replay_seeds")) + [replay_seed])
    state["pending_replay_seeds"] = pending
    seed_history = list_value(state.get("seed_history"))
    seed_history.append(
        {
            "seed": replay_seed,
            "requested_count": payload["requested_count"],
            "count": payload["count"],
            "boundary_available": payload["boundary_available"],
            "depth_available": payload["depth_available"],
            "random_count": payload["random_count"],
        }
    )
    state["seed_history"] = seed_history
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {}
    return json.loads(state_path.read_text(encoding="utf-8"))


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


def collect_sources(repos: list[Path], specs: list[Path]) -> list[SourceFile]:
    sources: dict[str, SourceFile] = {}
    use_root_prefix = len(repos) > 1
    for repo in repos:
        for path in listed_files(repo):
            if not path.exists() or not path.is_file():
                continue
            source = source_file(repo, path, use_root_prefix=use_root_prefix)
            sources[source.label] = source
    for spec in specs:
        if spec.exists() and spec.is_file() and include_path(spec):
            source = source_file(spec.parent, spec)
            sources[f"spec:{source.path.as_posix()}"] = source
    return sorted(sources.values(), key=lambda item: item.label)


def listed_files(root: Path) -> list[Path]:
    git_files = git_ls_files(root)
    if git_files:
        return [root / path for path in git_files if include_path(path)]
    return sorted(path for path in root.rglob("*") if path.is_file() and include_path(path.relative_to(root)))


def git_ls_files(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return []
    return [Path(line) for line in result.stdout.splitlines() if line]


def include_path(path: Path) -> bool:
    if any(part in SKIP_PARTS for part in path.parts):
        return False
    return path.suffix in TEXT_EXTENSIONS or path.name in {"pom.xml", "go.mod", "README", "Makefile"}


def source_file(root: Path, path: Path, *, use_root_prefix: bool = False) -> SourceFile:
    text = path.read_text(encoding="utf-8", errors="replace")
    label = label_for(root, path, use_root_prefix=use_root_prefix)
    return SourceFile(root=root, path=path, label=label, kind=kind_for(path), lines=line_count(text))


def label_for(root: Path, path: Path, *, use_root_prefix: bool = False) -> str:
    try:
        label = path.relative_to(root).as_posix()
    except ValueError:
        label = path.as_posix()
    if use_root_prefix:
        return f"{root.name}/{label}"
    return label


def line_count(text: str) -> int:
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0)


def kind_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return "doc"
    if suffix in {".java", ".kt", ".py", ".go", ".js", ".ts", ".tsx", ".jsx"}:
        return "code"
    if suffix in {".xml", ".json", ".yaml", ".yml", ".toml", ".properties"}:
        return "config"
    if suffix in {".sh", ".bash", ".bats"}:
        return "script"
    return "other"


def collect_depth_refs(contracts_dir: Path, breadth_sources: list[SourceFile], repos: list[Path]) -> list[DepthReference]:
    if not contracts_dir.exists():
        return []
    by_label = {source.label: source for source in breadth_sources}
    refs: list[DepthReference] = []
    for path in sorted(contracts_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        reason_prefix = "coverage gap" if path.name == "COVERAGE.md" else "existing contract evidence"
        if path.name == "COVERAGE.md":
            refs.extend(coverage_gap_refs(contracts_dir, path, text))
        for ref_text, line_text in REFERENCE_RE.findall(text):
            source = resolve_source(ref_text, by_label, repos)
            if source is None:
                continue
            line = int(line_text) if line_text else None
            refs.append(DepthReference(source=source, line=line, reason=f"{reason_prefix} in {path.name}"))
    return refs


def collect_boundary_refs(
    contracts_dir: Path | None,
    breadth_sources: list[SourceFile],
    repos: list[Path],
    *,
    write_inventory: bool,
    reuse: bool,
) -> list[BoundaryReference]:
    boundary_inventory = load_boundary_inventory_module()
    inventory_path = boundary_inventory.default_inventory_path(contracts_dir) if contracts_dir else None
    inventory = boundary_inventory.build_inventory(
        repos,
        contracts_dir=contracts_dir,
        existing_path=inventory_path,
        reuse=reuse,
        write=write_inventory,
    )
    by_label = {source.label: source for source in breadth_sources}
    by_rel = {label_without_root(source.label): source for source in breadth_sources}
    refs: list[BoundaryReference] = []
    for boundary in inventory.get("boundaries", []):
        if boundary.get("status", "active") != "active":
            continue
        source = by_label.get(str(boundary.get("path", ""))) or by_rel.get(str(boundary.get("repo_relative_path", "")))
        if source is None:
            continue
        line_range = boundary.get("line_range", [1, 1])
        try:
            start_line = int(line_range[0])
            end_line = int(line_range[1])
        except (TypeError, ValueError, IndexError):
            start_line, end_line = 1, min(source.lines, 1)
        refs.append(BoundaryReference(source=source, start_line=start_line, end_line=end_line, boundary=boundary))
    return sorted(
        refs,
        key=lambda ref: (
            evidence_role_rank(str(ref.boundary.get("evidence_role", ""))),
            -float(ref.boundary.get("confidence", 0)),
            str(ref.boundary.get("boundary_type", "")),
            ref.source.label,
        ),
    )


def label_without_root(label: str) -> str:
    parts = label.split("/", 1)
    return parts[1] if len(parts) == 2 else label


def evidence_role_rank(role: str) -> int:
    return {
        "production_anchor": 0,
        "spec_anchor": 1,
        "support_code": 2,
        "test_signal": 3,
    }.get(role, 4)


def coverage_gap_refs(contracts_dir: Path, path: Path, text: str) -> list[DepthReference]:
    gap_source = source_file(contracts_dir, path)
    refs: list[DepthReference] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        if any(word in lowered for word in ("gap", "missing", "uncovered", "unknown", "todo")):
            refs.append(DepthReference(source=gap_source, line=line_number, reason="known coverage gap in COVERAGE.md"))
    return refs


def resolve_source(ref_text: str, by_label: dict[str, SourceFile], repos: list[Path]) -> SourceFile | None:
    normalized = ref_text.strip()
    if normalized in by_label:
        return by_label[normalized]
    matches = [source for label, source in by_label.items() if label.endswith("/" + normalized)]
    if len(matches) == 1:
        return matches[0]
    ref_path = Path(normalized)
    if ref_path.is_absolute() and ref_path.exists() and include_path(ref_path):
        return source_file(ref_path.parent, ref_path)
    repo_matches = [
        (repo, repo / normalized)
        for repo in repos
        if (repo / normalized).exists() and (repo / normalized).is_file() and include_path(repo / normalized)
    ]
    if len(repo_matches) == 1:
        repo, path = repo_matches[0]
        return source_file(repo, path)
    return None


def select_seeds(
    rng: random.Random,
    breadth_sources: list[SourceFile],
    depth_refs: list[DepthReference],
    count: int,
    window: int,
    boundary_refs: list[BoundaryReference] | None = None,
    random_count: int = 0,
) -> list[dict]:
    if count <= 0:
        return []
    seeds: list[dict] = []
    boundary_refs = boundary_refs or []
    gap_refs = [ref for ref in depth_refs if ref.reason.startswith("known coverage gap")]
    remaining_count = count
    if gap_refs:
        seeds.append(depth_seed(rng, rng.choice(gap_refs), window))
        remaining_count -= 1
    for ref in selected_boundary_refs(rng, boundary_refs, remaining_count):
        seeds.append(boundary_seed(ref))
        remaining_count -= 1
    depth_only_refs = [ref for ref in depth_refs if not ref.reason.startswith("known coverage gap")]
    for ref in selected_depth_refs(rng, depth_only_refs, remaining_count):
        seeds.append(depth_seed(rng, ref, window))
        remaining_count -= 1
    explicit_random_count = min(max(random_count, 0), max(remaining_count, 0))
    strategies = strategy_plan(rng, explicit_random_count, False)
    for strategy in strategies:
        if strategy == "breadth" and breadth_sources:
            seeds.append(breadth_seed(rng, rng.choice(breadth_sources), window))
    rng.shuffle(seeds)
    return seeds


def selected_boundary_refs(rng: random.Random, boundary_refs: list[BoundaryReference], count: int) -> list[BoundaryReference]:
    if count <= 0 or not boundary_refs:
        return []
    production = [ref for ref in boundary_refs if ref.boundary.get("evidence_role") in {"production_anchor", "spec_anchor"}]
    support = [ref for ref in boundary_refs if ref.boundary.get("evidence_role") not in {"production_anchor", "spec_anchor"}]
    selected = weighted_sample(rng, production, min(count, len(production)))
    remaining = count - len(selected)
    if remaining > 0:
        selected.extend(weighted_sample(rng, support, min(remaining, len(support))))
    return selected


def selected_depth_refs(rng: random.Random, depth_refs: list[DepthReference], count: int) -> list[DepthReference]:
    if count <= 0 or not depth_refs:
        return []
    shuffled = list(depth_refs)
    rng.shuffle(shuffled)
    return shuffled[:count]


def weighted_sample(rng: random.Random, refs: list, count: int) -> list:
    if count <= 0 or not refs:
        return []
    pool = list(refs)
    rng.shuffle(pool)
    pool.sort(key=lambda ref: -float(ref.boundary.get("confidence", 0)) if hasattr(ref, "boundary") else 0)
    return pool[:count]


def strategy_plan(rng: random.Random, count: int, has_depth: bool) -> list[str]:
    if not has_depth:
        return ["breadth"] * count
    if count == 1:
        return [rng.choice(["breadth", "depth"])]
    plan = ["breadth", "depth"]
    plan.extend(rng.choice(["breadth", "depth"]) for _ in range(count - 2))
    rng.shuffle(plan)
    return plan


def breadth_seed(rng: random.Random, source: SourceFile, window: int) -> dict:
    start, end = random_window(rng, source.lines, window)
    return seed_payload(
        strategy="breadth",
        source=source,
        start=start,
        end=end,
        reason="random breadth sample from repository/spec inventory",
    )


def depth_seed(rng: random.Random, ref: DepthReference, window: int) -> dict:
    if ref.line is None:
        start, end = random_window(rng, ref.source.lines, window)
    else:
        start, end = centered_window(rng, ref.line, ref.source.lines, window)
    return seed_payload(strategy="depth", source=ref.source, start=start, end=end, reason=ref.reason)


def boundary_seed(ref: BoundaryReference) -> dict:
    payload = seed_payload(
        strategy="boundary",
        source=ref.source,
        start=ref.start_line,
        end=ref.end_line,
        reason=str(ref.boundary.get("reason", "source-anchored boundary inventory match")),
    )
    for key in (
        "boundary_id",
        "boundary_type",
        "symbol",
        "matcher_id",
        "confidence",
        "trace_direction",
        "evidence_role",
        "source_hash",
        "snippet_hash",
        "project_profile_id",
    ):
        if key in ref.boundary:
            payload[key] = ref.boundary[key]
    return payload


def random_window(rng: random.Random, lines: int, window: int) -> tuple[int, int]:
    if lines <= 0:
        return 1, 1
    size = min(lines, window)
    start = rng.randint(1, max(1, lines - size + 1))
    return start, start + size - 1


def centered_window(rng: random.Random, line: int, lines: int, window: int) -> tuple[int, int]:
    if lines <= 0:
        return 1, 1
    size = min(lines, window)
    jitter = rng.randint(-(size // 4), size // 4)
    midpoint = min(max(line + jitter, 1), lines)
    start = min(max(midpoint - size // 2, 1), max(1, lines - size + 1))
    return start, start + size - 1


def seed_payload(strategy: str, source: SourceFile, start: int, end: int, reason: str) -> dict:
    return {
        "strategy": strategy,
        "path": source.label,
        "kind": source.kind,
        "start_line": start,
        "end_line": end,
        "reason": reason,
    }


if __name__ == "__main__":
    raise SystemExit(main())
