#!/usr/bin/env python3
"""Build a deterministic local repository/specification inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


SKIP_PARTS = {".git", "target", "node_modules", ".idea", ".gradle", "build", "dist"}
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


@dataclass(frozen=True)
class FileRecord:
    path: str
    size: int
    lines: int
    sha256: str
    kind: str


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory local repos and specs for contract extraction or reconciliation.")
    parser.add_argument("--repo", action="append", default=[], help="Local repository path. May be repeated.")
    parser.add_argument("--spec", action="append", default=[], help="Local specification file path. May be repeated.")
    parser.add_argument("--output", help="Optional JSON output path.")
    args = parser.parse_args()

    repos = [Path(repo).resolve() for repo in args.repo] or [Path.cwd()]
    specs = [Path(spec).resolve() for spec in args.spec]
    payload = {
        "repos": [inventory_repo(repo) for repo in repos],
        "specs": [inventory_spec(spec) for spec in specs],
    }
    payload["inventory_hash"] = stable_hash(payload)

    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


def inventory_repo(root: Path) -> dict:
    files = [file_record(root, path) for path in listed_files(root)]
    files.sort(key=lambda item: item.path)
    return {
        "root": str(root),
        "git": (root / ".git").exists(),
        "files": [record.__dict__ for record in files],
        "summary": summarize(files),
    }


def inventory_spec(path: Path) -> dict:
    root = path.parent
    record = file_record(root, path)
    return {"root": str(root), "file": record.__dict__}


def listed_files(root: Path) -> list[Path]:
    git_files = git_ls_files(root)
    if git_files:
        return [root / path for path in git_files if include_path(Path(path))]
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


def file_record(root: Path, path: Path) -> FileRecord:
    data = path.read_bytes()
    rel = path.relative_to(root).as_posix()
    text = data.decode("utf-8", errors="replace")
    return FileRecord(
        path=rel,
        size=len(data),
        lines=text.count("\n") + (1 if text and not text.endswith("\n") else 0),
        sha256=hashlib.sha256(data).hexdigest(),
        kind=kind_for(path),
    )


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


def summarize(files: list[FileRecord]) -> dict:
    summary: dict[str, int] = {"total": len(files)}
    for record in files:
        summary[record.kind] = summary.get(record.kind, 0) + 1
    return summary


def stable_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
