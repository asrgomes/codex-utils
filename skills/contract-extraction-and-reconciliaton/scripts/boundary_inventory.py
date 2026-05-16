#!/usr/bin/env python3
"""Build a source-anchored inventory of likely contract boundaries."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


MATCHER_VERSION = "boundary-inventory-v1"
INVENTORY_NAME = ".boundary-inventory.json"
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
    ".sh",
    ".bash",
    ".bats",
    ".xml",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".properties",
    ".gradle",
    ".md",
    ".txt",
    ".sql",
}
MANIFEST_NAMES = {
    "pom.xml",
    "settings.gradle",
    "settings.gradle.kts",
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "package.json",
    "tsconfig.json",
    "pnpm-workspace.yaml",
}
TEST_PARTS = {"test", "tests", "__tests__", "spec", "specs"}
SUPPORT_WORDS = ("mock", "fake", "stub", "fixture", "testkit", "harness", "simulator", "inmemory")


@dataclass(frozen=True)
class SourceFile:
    root: Path
    path: Path
    label: str
    rel: str
    text: str
    lines: list[str]
    source_hash: str


@dataclass(frozen=True)
class Matcher:
    matcher_id: str
    boundary_type: str
    pattern: re.Pattern[str]
    trace_direction: str
    confidence: float
    extensions: tuple[str, ...] = ()
    path_keywords: tuple[str, ...] = ()


MATCHERS = [
    Matcher("java-spring-request-mapping", "rest_controller", re.compile(r"@\w*(?:Get|Post|Put|Patch|Delete|Request)Mapping\b|@RestController\b|@Controller\b"), "inbound", 0.93, (".java", ".kt")),
    Matcher("java-jax-rs-path", "rest_controller", re.compile(r"@(GET|POST|PUT|PATCH|DELETE|Path)\b"), "inbound", 0.86, (".java", ".kt")),
    Matcher("py-web-route", "rest_controller", re.compile(r"@\w+\.(?:get|post|put|patch|delete|route)\s*\("), "inbound", 0.86, (".py",)),
    Matcher("go-http-route", "rest_controller", re.compile(r"\b(?:http\.)?HandleFunc\s*\(|\b(?:GET|POST|PUT|PATCH|DELETE)\s*\("), "inbound", 0.78, (".go",)),
    Matcher("ts-http-route", "rest_controller", re.compile(r"\b(?:app|router)\.(?:get|post|put|patch|delete|use)\s*\(|@(?:Controller|Get|Post|Put|Patch|Delete)\b"), "inbound", 0.82, (".js", ".ts", ".tsx", ".jsx")),
    Matcher("java-servlet-filter", "servlet_filter", re.compile(r"@Web(?:Servlet|Filter)\b|extends\s+HttpServlet\b|implements\s+Filter\b"), "inbound", 0.9, (".java",)),
    Matcher("socket-websocket", "socket", re.compile(r"WebSocket|@ServerEndpoint\b|@OnMessage\b|socket\.io|websockets\.serve|net\.Listen\s*\("), "bidirectional", 0.82, (".java", ".kt", ".py", ".go", ".js", ".ts", ".tsx", ".jsx")),
    Matcher("ui-route-action", "ui_route_action", re.compile(r"<Route\b|createBrowserRouter\s*\(|getServerSideProps\b|getStaticProps\b|\"use server\"|action\s*[:=]\s*(?:async\s*)?\("), "inbound", 0.72, (".js", ".ts", ".tsx", ".jsx")),
    Matcher("cli-entrypoint", "cli_entrypoint", re.compile(r"if\s+__name__\s*==\s*['\"]__main__['\"]|argparse\.ArgumentParser|click\.command|typer\.Typer|func\s+main\s*\(|public\s+static\s+void\s+main\s*\(|cobra\.Command|commander|yargs"), "inbound", 0.82, (".py", ".go", ".java", ".js", ".ts", ".sh", ".bash")),
    Matcher("file-io-boundary", "file_io", re.compile(r"\b(?:open|Path|Files\.(?:read|write|newInputStream|newOutputStream)|fs\.(?:readFile|writeFile|createReadStream|createWriteStream)|os\.(?:Open|Create)|WatchService|chokidar\.watch|csv\.reader)\b"), "bidirectional", 0.68, (".java", ".kt", ".py", ".go", ".js", ".ts", ".tsx", ".jsx")),
    Matcher("db-boundary", "database", re.compile(r"@Repository\b|JpaRepository\b|CrudRepository\b|JdbcTemplate\b|EntityManager\b|create table\b|alter table\b|liquibase|flyway", re.IGNORECASE), "outbound", 0.78, (".java", ".kt", ".py", ".go", ".js", ".ts", ".sql", ".xml", ".yaml", ".yml")),
    Matcher("message-boundary", "message", re.compile(r"@(?:Kafka|Jms|Rabbit)Listener\b|MessageListener\b|KafkaConsumer\b|KafkaProducer\b|SqsListener\b|celery\.task|@shared_task|pubsub|nats\.|amqp|rabbitmq", re.IGNORECASE), "bidirectional", 0.84, (".java", ".kt", ".py", ".go", ".js", ".ts", ".tsx", ".jsx")),
    Matcher("scheduler-timer", "scheduler_timer", re.compile(r"@Scheduled\b|CronTrigger\b|Quartz|ScheduledExecutor|APScheduler|celery\.beat|cron\.schedule|setInterval\s*\(|time\.NewTicker|time\.Tick\("), "inbound", 0.82, (".java", ".kt", ".py", ".go", ".js", ".ts", ".tsx", ".jsx")),
    Matcher("os-signal", "os_signal", re.compile(r"signal\.Notify|signal\.signal|process\.on\s*\(\s*['\"]SIG|addShutdownHook|trap\s+['\"A-Za-z0-9_ -]+SIG"), "inbound", 0.88, (".java", ".py", ".go", ".js", ".ts", ".sh", ".bash")),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a source-anchored boundary inventory for contract extraction.")
    parser.add_argument("--repo", action="append", default=[], help="Local repository path. May be repeated.")
    parser.add_argument("--contracts", help="Contracts directory for the default .boundary-inventory.json path.")
    parser.add_argument("--output", help="Explicit JSON output path.")
    parser.add_argument("--write", action="store_true", help="Write the inventory JSON.")
    parser.add_argument("--reuse", action="store_true", help="Reuse unchanged source-anchored boundaries from an existing inventory.")
    parser.add_argument("--format", choices=("json",), default="json")
    args = parser.parse_args()

    repos = [Path(repo).resolve() for repo in args.repo] or [Path.cwd()]
    contracts_dir = Path(args.contracts).resolve() if args.contracts else None
    output = Path(args.output).resolve() if args.output else default_inventory_path(contracts_dir)
    payload = build_inventory(repos, contracts_dir=contracts_dir, existing_path=output, reuse=args.reuse, write=args.write)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def default_inventory_path(contracts_dir: Path | None) -> Path | None:
    if contracts_dir is None:
        return None
    return contracts_dir / INVENTORY_NAME


def build_inventory(
    repos: list[Path],
    *,
    contracts_dir: Path | None = None,
    existing_path: Path | None = None,
    reuse: bool = False,
    write: bool = False,
) -> dict:
    roots = [repo.resolve() for repo in repos]
    existing = read_json(existing_path) if reuse and existing_path else {}
    existing_by_path = group_existing_by_path(existing)
    use_root_prefix = len(roots) > 1
    inventory_repos = []
    active_boundaries: list[dict] = []
    stale_boundaries: list[dict] = []
    for root in roots:
        sources = collect_sources(root, use_root_prefix=use_root_prefix)
        profile = profile_repo(root, sources)
        reused, scanned, stale = detect_repo_boundaries(root, sources, profile, existing_by_path, reuse=reuse)
        active_boundaries.extend(reused)
        active_boundaries.extend(scanned)
        stale_boundaries.extend(stale)
        inventory_repos.append(
            {
                "root": str(root),
                "project_profile": profile,
                "files_considered": len(sources),
                "boundaries": len(reused) + len(scanned),
                "reused_boundaries": len(reused),
                "scanned_boundaries": len(scanned),
            }
        )
    current_paths = {
        value
        for root in roots
        for source in collect_sources(root, use_root_prefix=use_root_prefix)
        for value in (source.label, source.rel)
    }
    stale_boundaries.extend(missing_file_stale_boundaries(existing_by_path, current_paths))
    boundaries = sorted(active_boundaries + stale_boundaries, key=lambda item: (item.get("status", ""), item["path"], item["boundary_type"], item["boundary_id"]))
    payload = {
        "schema_version": 1,
        "matcher_version": MATCHER_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "discovery_tools": discovery_tools(),
        "repos": inventory_repos,
        "boundaries": boundaries,
        "summary": summarize(boundaries),
    }
    payload["inventory_hash"] = stable_hash(
        {
            "matcher_version": payload["matcher_version"],
            "repos": payload["repos"],
            "boundaries": [
                {
                    key: boundary.get(key)
                    for key in (
                        "boundary_id",
                        "boundary_type",
                        "path",
                        "line_range",
                        "symbol",
                        "matcher_id",
                        "evidence_role",
                        "source_hash",
                        "snippet_hash",
                        "status",
                    )
                }
                for boundary in boundaries
            ],
        }
    )
    for boundary in boundaries:
        boundary["detected_at_inventory_hash"] = payload["inventory_hash"]
    output = existing_path or default_inventory_path(contracts_dir)
    if write and output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def collect_sources(root: Path, *, use_root_prefix: bool) -> list[SourceFile]:
    sources: list[SourceFile] = []
    for path in listed_files(root):
        if not path.exists() or not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        label = f"{root.name}/{rel}" if use_root_prefix else rel
        sources.append(
            SourceFile(
                root=root,
                path=path,
                label=label,
                rel=rel,
                text=text,
                lines=text.splitlines(),
                source_hash=sha256_text(text),
            )
        )
    return sorted(sources, key=lambda item: item.label)


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
    return path.suffix in TEXT_EXTENSIONS or path.name in MANIFEST_NAMES or path.name in {"README", "Makefile"}


def profile_repo(root: Path, sources: list[SourceFile]) -> dict:
    rels = {source.rel for source in sources}
    ecosystems: list[str] = []
    structure: dict[str, object] = {}
    if "pom.xml" in rels or any(rel.endswith("/pom.xml") for rel in rels):
        ecosystems.append("maven")
        root_pom = source_text(sources, "pom.xml")
        modules = sorted(set(re.findall(r"<module>\s*([^<]+)\s*</module>", root_pom)))
        structure["maven"] = {
            "multi_module": bool(modules),
            "modules": modules,
            "pom_count": sum(1 for rel in rels if rel == "pom.xml" or rel.endswith("/pom.xml")),
        }
    if any(rel in rels for rel in ("settings.gradle", "settings.gradle.kts", "build.gradle", "build.gradle.kts")):
        ecosystems.append("gradle")
        settings = source_text(sources, "settings.gradle") + "\n" + source_text(sources, "settings.gradle.kts")
        includes = sorted(set(re.findall(r"include\s+(.+)", settings)))
        structure["gradle"] = {
            "multi_project": bool(includes),
            "includes": includes,
            "build_count": sum(1 for rel in rels if rel.endswith(("build.gradle", "build.gradle.kts"))),
        }
    if "go.mod" in rels or any(rel.endswith(".go") for rel in rels):
        ecosystems.append("golang")
        packages = sorted({str(Path(rel).parent) for rel in rels if rel.endswith(".go") and not rel.endswith("_test.go")})
        structure["golang"] = {
            "module": module_name(source_text(sources, "go.mod")),
            "packages": packages[:200],
            "has_cmd": any(rel.startswith("cmd/") for rel in rels),
        }
    if any(rel in rels for rel in ("pyproject.toml", "setup.py", "setup.cfg")) or any(rel.endswith(".py") for rel in rels):
        ecosystems.append("python")
        structure["python"] = {
            "src_layout": any(rel.startswith("src/") for rel in rels),
            "test_paths": sorted(rel for rel in rels if evidence_role_for(rel, source_text(sources, rel)) == "test_signal")[:200],
        }
    if "package.json" in rels or "tsconfig.json" in rels or any(rel.endswith((".ts", ".tsx", ".js", ".jsx")) for rel in rels):
        ecosystems.append("typescript")
        package_json = source_text(sources, "package.json")
        structure["typescript"] = {
            "has_package_json": bool(package_json),
            "has_tsconfig": "tsconfig.json" in rels,
            "workspace_hint": "workspaces" in package_json or "pnpm-workspace.yaml" in rels,
            "has_app_dir": any(part in rel.split("/") for rel in rels for part in ("app", "pages")),
        }
    profile = {
        "ecosystems": sorted(set(ecosystems)),
        "structure": structure,
    }
    profile["project_profile_id"] = "profile-" + stable_hash(profile)[:12]
    return profile


def source_text(sources: list[SourceFile], rel: str) -> str:
    for source in sources:
        if source.rel == rel:
            return source.text
    return ""


def module_name(go_mod: str) -> str:
    match = re.search(r"^module\s+(\S+)", go_mod, re.MULTILINE)
    return match.group(1) if match else ""


def detect_repo_boundaries(
    root: Path,
    sources: list[SourceFile],
    profile: dict,
    existing_by_path: dict[str, list[dict]],
    *,
    reuse: bool,
) -> tuple[list[dict], list[dict], list[dict]]:
    reused: list[dict] = []
    scanned: list[dict] = []
    stale: list[dict] = []
    for source in sources:
        existing = existing_by_path.get(source.label, []) + existing_by_path.get(source.rel, [])
        reusable = [
            with_reuse_marker(boundary)
            for boundary in existing
            if reuse
            and boundary.get("source_hash") == source.source_hash
            and boundary.get("matcher_version") == MATCHER_VERSION
            and boundary.get("status", "active") == "active"
        ]
        if reusable:
            reused.extend(dedupe_boundaries(reusable))
            continue
        fresh = detect_source_boundaries(source, profile)
        scanned.extend(fresh)
        if reuse and existing:
            fresh_ids = {item["boundary_id"] for item in fresh}
            for old in existing:
                if old.get("boundary_id") not in fresh_ids and old.get("status", "active") == "active":
                    stale.append(stale_boundary(old, "source changed or matcher no longer matches"))
    return dedupe_boundaries(reused), dedupe_boundaries(scanned), dedupe_boundaries(stale)


def detect_source_boundaries(source: SourceFile, profile: dict) -> list[dict]:
    boundaries: list[dict] = []
    role = evidence_role_for(source.rel, source.text)
    for matcher in MATCHERS:
        if matcher.extensions and source.path.suffix not in matcher.extensions:
            continue
        if matcher.path_keywords and not any(keyword in source.rel.lower() for keyword in matcher.path_keywords):
            continue
        for match in matcher.pattern.finditer(source.text):
            line = line_number_at(source.text, match.start())
            line_range = line_window(line, len(source.lines), window=5)
            symbol = symbol_for(source, line, match)
            snippet = "\n".join(source.lines[line_range[0] - 1 : line_range[1]])
            boundary_id = boundary_id_for(source.rel, matcher.boundary_type, symbol, matcher.matcher_id)
            boundaries.append(
                {
                    "boundary_id": boundary_id,
                    "boundary_type": matcher.boundary_type,
                    "path": source.label,
                    "repo_relative_path": source.rel,
                    "repo_root": str(source.root),
                    "line_range": list(line_range),
                    "symbol": symbol,
                    "matcher_id": matcher.matcher_id,
                    "matcher_version": MATCHER_VERSION,
                    "confidence": matcher.confidence,
                    "trace_direction": matcher.trace_direction,
                    "evidence_role": role,
                    "source_hash": source.source_hash,
                    "snippet_hash": sha256_text(snippet),
                    "project_profile_id": profile["project_profile_id"],
                    "status": "active",
                    "reused": False,
                    "reason": f"{matcher.boundary_type} boundary matched by {matcher.matcher_id}",
                }
            )
    return dedupe_boundaries(boundaries)


def evidence_role_for(rel: str, text: str) -> str:
    lowered = rel.lower()
    parts = set(Path(lowered).parts)
    name = Path(lowered).name
    suffix = Path(lowered).suffix
    if suffix in {".md", ".txt"} and any(part in parts for part in ("docs", "doc", "adr", "specs")):
        return "spec_anchor"
    if (
        TEST_PARTS & parts
        or "/src/test/" in f"/{lowered}/"
        or name.endswith("_test.go")
        or name.startswith("test_")
        or ".test." in name
        or ".spec." in name
        or suffix == ".bats"
    ):
        return "test_signal"
    support_by_name = any(word in lowered for word in SUPPORT_WORDS)
    support_by_text = bool(re.search(r"\b(Mockito|pytest|unittest|jest|vitest|TestCase|assert|fixture|mock|fake|stub)\b", text))
    if support_by_name and ("/src/main/" in f"/{lowered}/" or support_by_text):
        return "support_code"
    return "production_anchor"


def line_number_at(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def line_window(line: int, total_lines: int, *, window: int) -> tuple[int, int]:
    if total_lines <= 0:
        return 1, 1
    half = max(0, window // 2)
    start = max(1, line - half)
    end = min(total_lines, line + half)
    return start, end


def symbol_for(source: SourceFile, line: int, match: re.Match[str]) -> str:
    search_start = max(0, line - 8)
    search_end = min(len(source.lines), line + 3)
    nearby = "\n".join(source.lines[search_start:search_end])
    patterns = [
        r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\binterface\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\bfunc\s+(?:\([^)]+\)\s*)?([A-Za-z_][A-Za-z0-9_]*)",
        r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\b(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"\b(?:public|private|protected)?\s*(?:static\s+)?[A-Za-z0-9_<>\[\]]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
    ]
    for pattern in patterns:
        found = re.search(pattern, nearby)
        if found:
            return found.group(1)
    matched = match.group(0).strip().replace("\n", " ")
    return matched[:80]


def boundary_id_for(rel: str, boundary_type: str, symbol: str, matcher_id: str) -> str:
    digest = stable_hash({"path": rel, "boundary_type": boundary_type, "symbol": symbol, "matcher_id": matcher_id})[:16]
    return f"boundary-{digest}"


def group_existing_by_path(existing: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for boundary in existing.get("boundaries", []) if isinstance(existing, dict) else []:
        if not isinstance(boundary, dict):
            continue
        for key in ("path", "repo_relative_path"):
            value = boundary.get(key)
            if isinstance(value, str) and value:
                grouped.setdefault(value, []).append(boundary)
    return grouped


def with_reuse_marker(boundary: dict) -> dict:
    reused = dict(boundary)
    reused["status"] = "active"
    reused["reused"] = True
    reused["matcher_version"] = MATCHER_VERSION
    return reused


def stale_boundary(boundary: dict, reason: str) -> dict:
    stale = dict(boundary)
    stale["status"] = "stale"
    stale["reused"] = False
    stale["stale_reason"] = reason
    stale["matcher_version"] = MATCHER_VERSION
    return stale


def missing_file_stale_boundaries(existing_by_path: dict[str, list[dict]], current_paths: set[str]) -> list[dict]:
    stale: list[dict] = []
    seen: set[str] = set()
    for path, boundaries in existing_by_path.items():
        if path in current_paths:
            continue
        for boundary in boundaries:
            boundary_id = str(boundary.get("boundary_id", ""))
            if not boundary_id or boundary_id in seen or boundary.get("status") == "stale":
                continue
            seen.add(boundary_id)
            stale.append(stale_boundary(boundary, "source file no longer exists"))
    return stale


def dedupe_boundaries(boundaries: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for boundary in boundaries:
        by_id[boundary["boundary_id"]] = boundary
    return sorted(by_id.values(), key=lambda item: (item["path"], item["boundary_type"], item["boundary_id"]))


def summarize(boundaries: list[dict]) -> dict:
    by_type: dict[str, int] = {}
    by_role: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for boundary in boundaries:
        by_type[boundary["boundary_type"]] = by_type.get(boundary["boundary_type"], 0) + 1
        by_role[boundary["evidence_role"]] = by_role.get(boundary["evidence_role"], 0) + 1
        by_status[boundary.get("status", "active")] = by_status.get(boundary.get("status", "active"), 0) + 1
    return {
        "total": len(boundaries),
        "by_boundary_type": by_type,
        "by_evidence_role": by_role,
        "by_status": by_status,
    }


def discovery_tools() -> dict:
    return {
        "file_listing": "git ls-files" if shutil.which("git") else "python rglob",
        "available_fast_search": "rg --json" if shutil.which("rg") else "",
        "matcher_engine": "python regex scan over profile-scoped text files",
        "matcher_version": MATCHER_VERSION,
    }


def read_json(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
