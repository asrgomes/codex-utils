#!/usr/bin/env python3
"""Select randomized code/spec slices for embryonic contract candidates."""

from __future__ import annotations

import argparse
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
}
REFERENCE_RE = re.compile(r"`([^`:\n]+)(?::(\d+))?`")


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Randomly select embryonic contract candidate seeds.")
    parser.add_argument("--repo", action="append", default=[], help="Local repository path. May be repeated.")
    parser.add_argument("--spec", action="append", default=[], help="Local specification file path. May be repeated.")
    parser.add_argument("--contracts", help="Existing contracts directory for depth-oriented seeds.")
    parser.add_argument("--count", type=int, default=12, help="Number of seeds to emit.")
    parser.add_argument("--window", type=int, default=30, help="Maximum line window per seed.")
    parser.add_argument("--seed", help="Replay seed. Omit for fresh randomness.")
    args = parser.parse_args()

    replay_seed = args.seed or secrets.token_hex(12)
    rng = random.Random(replay_seed)
    repos = [Path(repo).resolve() for repo in args.repo] or [Path.cwd()]
    specs = [Path(spec).resolve() for spec in args.spec]
    contracts_dir = Path(args.contracts).resolve() if args.contracts else None

    breadth_sources = collect_sources(repos, specs)
    depth_refs = collect_depth_refs(contracts_dir, breadth_sources, repos) if contracts_dir else []
    seeds = select_seeds(rng, breadth_sources, depth_refs, max(args.count, 0), max(args.window, 1))
    payload = {
        "seed": replay_seed,
        "requested_count": max(args.count, 0),
        "count": len(seeds),
        "depth_available": bool(depth_refs),
        "seeds": seeds,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def collect_sources(repos: list[Path], specs: list[Path]) -> list[SourceFile]:
    sources: dict[str, SourceFile] = {}
    for repo in repos:
        for path in listed_files(repo):
            if not path.exists() or not path.is_file():
                continue
            source = source_file(repo, path)
            sources[source.path.as_posix()] = source
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
    return path.suffix in TEXT_EXTENSIONS or path.name in {"pom.xml", "README", "Makefile"}


def source_file(root: Path, path: Path) -> SourceFile:
    text = path.read_text(encoding="utf-8", errors="replace")
    label = label_for(root, path)
    return SourceFile(root=root, path=path, label=label, kind=kind_for(path), lines=line_count(text))


def label_for(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def line_count(text: str) -> int:
    return text.count("\n") + (1 if text and not text.endswith("\n") else 0)


def kind_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        return "doc"
    if suffix in {".java", ".kt", ".py", ".js", ".ts", ".tsx", ".jsx"}:
        return "code"
    if suffix in {".xml", ".json", ".yaml", ".yml", ".toml", ".properties"}:
        return "config"
    if suffix == ".sh":
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
        for ref_text, line_text in REFERENCE_RE.findall(text):
            source = resolve_source(ref_text, by_label, repos)
            if source is None:
                continue
            line = int(line_text) if line_text else None
            refs.append(DepthReference(source=source, line=line, reason=f"{reason_prefix} in {path.name}"))
    return refs


def resolve_source(ref_text: str, by_label: dict[str, SourceFile], repos: list[Path]) -> SourceFile | None:
    normalized = ref_text.strip()
    if normalized in by_label:
        return by_label[normalized]
    for label, source in by_label.items():
        if label.endswith("/" + normalized):
            return source
    ref_path = Path(normalized)
    if ref_path.is_absolute() and ref_path.exists() and include_path(ref_path):
        return source_file(ref_path.parent, ref_path)
    for repo in repos:
        candidate = repo / normalized
        if candidate.exists() and candidate.is_file() and include_path(candidate):
            return source_file(repo, candidate)
    return None


def select_seeds(
    rng: random.Random,
    breadth_sources: list[SourceFile],
    depth_refs: list[DepthReference],
    count: int,
    window: int,
) -> list[dict]:
    if count <= 0 or not breadth_sources:
        return []
    seeds: list[dict] = []
    strategies = strategy_plan(rng, count, bool(depth_refs))
    for strategy in strategies:
        if strategy == "depth" and depth_refs:
            seeds.append(depth_seed(rng, rng.choice(depth_refs), window))
        else:
            seeds.append(breadth_seed(rng, rng.choice(breadth_sources), window))
    rng.shuffle(seeds)
    return seeds


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
