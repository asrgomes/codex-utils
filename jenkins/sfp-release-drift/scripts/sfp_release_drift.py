#!/usr/bin/env python3.12
"""Audit SFP AWS/OCI release-branch drift for configured Git repositories."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Mapping, Sequence, TextIO, TypedDict, cast
from urllib.parse import urlparse


AWS_MAJOR = 12
OCI_MAJOR = 26
BRANCH_RE: re.Pattern[str] = re.compile(r"^release/(?P<major>12|26)\.(?P<a>\d+)\.(?P<b>\d+)\.(?P<c>\d+)$")
GIT_OBJECT_RE: re.Pattern[str] = re.compile(r"^[0-9a-f]{40,64}$")
COMMIT_SEP = "\x1f"
ANSI_RESET = "\033[0m"
DEFAULT_MAX_COMMITS_PER_FINDING = 10
type Severity = Literal["DEBUG", "INFO", "WARN", "ERROR"]
type Status = Literal["pass", "fail"]
type BranchFamily = Literal["aws", "oci"]
type CheckName = Literal["config", "git", "fetch", "drift", "aws_to_oci", "aws_adjacent", "oci_adjacent"]
type Version = tuple[int, int, int, int]
type ConfigTable = Mapping[str, object]
SEVERITY_COLORS: dict[Severity, str] = {
    "DEBUG": "\033[2;90m",
    "WARN": "\033[33m",
    "ERROR": "\033[1;31m",
}


class Commit(TypedDict, total=False):
    """Commit metadata captured from `git log` for report rendering."""

    raw: str
    hash: str
    short_hash: str
    author: str
    date: str
    tree: str
    parents: list[str]
    subject: str


class Finding(TypedDict, total=False):
    """One drift, missing-branch, repository, or configuration finding."""

    type: str
    check: str
    repository: str
    repository_url: str
    from_branch: str
    to_branch: str
    commit_count: int
    commits: list[Commit]
    message: str


class IgnoredCommitGroup(TypedDict):
    """Branch-pair drift commits ignored after a no-op merge simulation."""

    check: CheckName
    repository: str
    repository_url: str
    from_branch: str
    to_branch: str
    commit_count: int
    commits: list[Commit]
    message: str


class SelectedBranches(TypedDict):
    """AWS and OCI release branches selected for one repository scan."""

    aws: list[str]
    oci: list[str]


class RepositoryReport(TypedDict):
    """Audit result for one configured Git repository."""

    repository: str
    repository_url: str
    status: Status
    selected_branches: SelectedBranches
    ignored_release_branches: list[str]
    findings: list[Finding]
    ignored_non_material_commits: list[IgnoredCommitGroup]


class AuditConfig(TypedDict):
    """Config values copied into the final report."""

    config_file: str
    tmp_dir: str
    max_versions: int
    ignore_non_material_commits: bool
    suppressed_branches: list[str]


class AuditReport(TypedDict):
    """Complete drift audit result rendered to Markdown, Slack, and exit status."""

    generated_at: str
    status: Status
    config: AuditConfig
    repositories: list[RepositoryReport]
    findings: list[Finding]
    ignored_non_material_commits: list[IgnoredCommitGroup]


class RuntimeConfig(TypedDict):
    """Validated TOML config used internally while running the audit."""

    config_file: Path
    verbose: bool
    tmp_dir: Path
    max_versions: int
    ignore_non_material_commits: bool
    suppressed_branches: list[str]
    repositories: list[str]
    output_report_file: Path
    slack_text_file: Path | None


@dataclass(frozen=True)
class ReleaseBranch:
    """Parsed release branch with a numeric version suitable for sorting."""

    name: str
    major: int
    version: Version


@dataclass(frozen=True)
class CliArgs:
    """Typed command-line arguments after argparse validation."""

    config: Path


class ProgressLogger:
    """Write severity-prefixed progress logs to stderr or a supplied stream."""

    def __init__(
        self,
        verbose: bool = False,
        stream: TextIO | None = None,
        use_color: bool | None = None,
    ) -> None:
        self.verbose = verbose
        self.stream = stream if stream is not None else sys.stderr
        self.use_color = terminal_supports_color(self.stream) if use_color is None else use_color

    def debug(self, message: str) -> None:
        """Log detailed diagnostic output only when verbose mode is enabled."""

        if self.verbose:
            self.log("DEBUG", message)

    def detail(self, message: str) -> None:
        """Backward-compatible alias for verbose diagnostic output."""

        self.debug(message)

    def info(self, message: str) -> None:
        """Log normal progress output."""

        self.log("INFO", message)

    def warn(self, message: str) -> None:
        """Log a non-fatal warning, such as detected branch drift."""

        self.log("WARN", message)

    def error(self, message: str) -> None:
        """Log an error that should make the audit fail."""

        self.log("ERROR", message)

    def log(self, severity: Severity, message: str) -> None:
        """Emit one human-readable log line, colorized when the stream supports it."""

        label = severity.ljust(5)
        line = f"{label} {message}"
        if self.use_color:
            color = SEVERITY_COLORS.get(severity)
            if color:
                line = f"{color}{line}{ANSI_RESET}"
        print(line, file=self.stream)


def terminal_supports_color(stream: TextIO) -> bool:
    """Return whether ANSI colors should be used for an output stream."""

    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def parse_args(argv: Sequence[str]) -> CliArgs:
    """Parse command-line arguments; `-f` is intentionally required."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-f",
        dest="config",
        required=True,
        type=Path,
        metavar="CONFIG.toml",
        help="TOML config file to load.",
    )
    namespace = parser.parse_args(argv)
    return CliArgs(config=namespace.config)


class ConfigError(ValueError):
    """Raised when the TOML config is missing, invalid, or unsafe."""

    pass


def config_error_report(config_file: Path, message: str) -> AuditReport:
    """Build a report object for configuration failures."""

    return {
        "generated_at": utc_timestamp(),
        "status": "fail",
        "config": {
            "config_file": str(config_file),
            "tmp_dir": "",
            "max_versions": 0,
            "ignore_non_material_commits": False,
            "suppressed_branches": [],
        },
        "repositories": [],
        "findings": [
            {
                "type": "config_error",
                "check": "config",
                "message": message,
            }
        ],
        "ignored_non_material_commits": [],
    }


def utc_timestamp() -> str:
    """Return a second-precision UTC timestamp for reports."""

    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_config(path: Path) -> RuntimeConfig:
    """Load and validate the TOML config used by the drift audit."""

    config_file = path.expanduser()
    config_dir = config_file.resolve().parent
    if not config_file.exists():
        raise ConfigError(f"Config file not found: {config_file}")
    if not config_file.is_file():
        raise ConfigError(f"Config path is not a file: {config_file}")

    try:
        with config_file.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {config_file}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read config file {config_file}: {exc}") from exc

    if "repsitories" in raw:
        raise ConfigError("Config key 'repsitories' is misspelled; use 'repositories'.")

    verbose = require_bool(raw, "verbose")
    tmp_dir = resolve_config_path(config_dir, require_string(raw, "tmp_dir"))
    max_versions = require_positive_int(raw, "max_versions")
    ignore_non_material_commits = optional_bool(raw, "ignore_non_material_commits", False)
    suppressed_branches = optional_string_list(raw, "suppressed_branches")
    repositories = require_repository_list(raw)
    output_report_file = resolve_config_path(config_dir, require_string(raw, "output_report_file"))
    if output_report_file.suffix != ".md":
        raise ConfigError("Config key 'output_report_file' must end with '.md'.")

    slack_text_file: Path | None = None
    if "slack_text_file" in raw:
        slack_text_file = resolve_config_path(config_dir, require_string(raw, "slack_text_file"))

    return {
        "config_file": config_file,
        "verbose": verbose,
        "tmp_dir": tmp_dir,
        "max_versions": max_versions,
        "ignore_non_material_commits": ignore_non_material_commits,
        "suppressed_branches": suppressed_branches,
        "repositories": repositories,
        "output_report_file": output_report_file,
        "slack_text_file": slack_text_file,
    }


def resolve_config_path(config_dir: Path, value: str) -> Path:
    """Resolve config-local relative paths and normalize `..` segments."""

    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (config_dir / path).resolve()


def require_bool(raw: ConfigTable, key: str) -> bool:
    """Read a required TOML boolean value."""

    value = require_key(raw, key)
    if not isinstance(value, bool):
        raise ConfigError(f"Config key '{key}' must be true or false.")
    return value


def optional_bool(raw: ConfigTable, key: str, default: bool) -> bool:
    """Read an optional TOML boolean value."""

    if key not in raw:
        return default
    value = raw[key]
    if not isinstance(value, bool):
        raise ConfigError(f"Config key '{key}' must be true or false.")
    return value


def optional_string_list(raw: ConfigTable, key: str) -> list[str]:
    """Read an optional TOML list of non-empty strings."""

    if key not in raw:
        return []
    value = raw[key]
    if not isinstance(value, list):
        raise ConfigError(f"Config key '{key}' must be a list of non-empty strings.")

    items: list[str] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"Config key '{key}' entry {index} must be a non-empty string.")
        items.append(item.strip())
    return items


def require_string(raw: ConfigTable, key: str) -> str:
    """Read a required TOML string value, rejecting blank strings."""

    value = require_key(raw, key)
    if not isinstance(value, str):
        raise ConfigError(f"Config key '{key}' must be a non-empty string.")
    value = value.strip()
    if not value:
        raise ConfigError(f"Config key '{key}' must be a non-empty string.")
    return value


def require_positive_int(raw: ConfigTable, key: str) -> int:
    """Read a required TOML positive integer value."""

    value = require_key(raw, key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"Config key '{key}' must be a positive integer.")
    return value


def require_key(raw: ConfigTable, key: str) -> object:
    """Read a required TOML key before validating its concrete type."""

    if key not in raw:
        raise ConfigError(f"Missing required config key '{key}'.")
    return raw[key]


def require_repository_list(raw: ConfigTable) -> list[str]:
    """Validate repository URLs and reject non-SSH inputs."""

    value = require_key(raw, "repositories")
    if not isinstance(value, list) or not value:
        raise ConfigError("Config key 'repositories' must be a non-empty list of SSH URLs.")

    repositories: list[str] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"Config key 'repositories' entry {index} must be a non-empty string.")
        repository = item.strip()
        parsed = urlparse(repository)
        if parsed.scheme != "ssh" or not parsed.netloc or not parsed.path:
            raise ConfigError(f"Config key 'repositories' entry {index} must be an ssh:// URL: {repository}")
        repositories.append(repository)
    return repositories


def parse_release_branch(name: str) -> ReleaseBranch | None:
    """Parse supported release branches, ignoring unrelated branch names."""

    match = BRANCH_RE.match(name)
    if not match:
        return None
    major = int(match.group("major"))
    version = (
        major,
        int(match.group("a")),
        int(match.group("b")),
        int(match.group("c")),
    )
    return ReleaseBranch(name=name, major=major, version=version)


def sort_newest_first(branches: Iterable[ReleaseBranch]) -> list[ReleaseBranch]:
    """Sort release branches numerically, newest version first."""

    return sorted(branches, key=lambda branch: branch.version, reverse=True)


def select_newest(branches: Iterable[ReleaseBranch], count: int) -> list[ReleaseBranch]:
    """Select the newest release branches from an already parsed branch set."""

    return sort_newest_first(branches)[:count]


def counterpart_oci_branch(aws_branch: ReleaseBranch) -> str:
    """Map `release/12.X.Y.Z` to its lockstep `release/26.X.Y.Z` branch."""

    if aws_branch.major != AWS_MAJOR:
        raise ValueError(f"Expected AWS release branch major {AWS_MAJOR}: {aws_branch.name}")
    _, a, b, c = aws_branch.version
    return f"release/{OCI_MAJOR}.{a}.{b}.{c}"


def commit_count_label(count: int) -> str:
    """Return a grammatically correct commit-count noun."""

    return "commit" if count == 1 else "commits"


def repo_display_name(url: str) -> str:
    """Derive a compact repository name from an SSH URL."""

    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    name = os.path.basename(path) or url.rstrip("/").split("/")[-1]
    return name[:-4] if name.endswith(".git") else name


def repo_work_dir(base: Path, index: int, url: str) -> Path:
    """Return a stable per-repository work directory under the temp root."""

    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    raw_name = repo_display_name(url)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw_name).strip("-") or "repo"
    return base / f"{index:03d}-{safe_name}-{digest}"


def run_git(repo_dir: Path, args: Sequence[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run a Git command in a repository and raise a concise error on failure."""

    result = subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return result


def set_origin_url(repo_dir: Path, url: str) -> None:
    """Add or update the `origin` remote for an initialized repository."""

    existing_origin = run_git(repo_dir, ["remote", "get-url", "origin"], check=False)
    if existing_origin.returncode == 0:
        run_git(repo_dir, ["remote", "set-url", "origin", url])
    else:
        run_git(repo_dir, ["remote", "add", "origin", url])


def ensure_repo_fetched(repo_dir: Path, url: str) -> None:
    """Initialize or update a local repo clone and fetch release branches only."""

    repo_dir.mkdir(parents=True, exist_ok=True)
    git_dir = repo_dir / ".git"
    if not git_dir.exists():
        init = subprocess.run(
            ["git", "init", str(repo_dir)],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if init.returncode != 0:
            raise RuntimeError(f"git init failed: {init.stderr.strip() or init.stdout.strip()}")
    set_origin_url(repo_dir, url)

    run_git(
        repo_dir,
        [
            "fetch",
            "--prune",
            "origin",
            "+refs/heads/release/*:refs/remotes/origin/release/*",
        ],
    )


def remote_release_branch_names(repo_dir: Path) -> list[str]:
    """List fetched remote release branch names without the `origin/` prefix."""

    result = run_git(
        repo_dir,
        ["for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/release"],
    )
    names: list[str] = []
    for line in result.stdout.splitlines():
        ref = line.strip()
        if ref.startswith("origin/"):
            names.append(ref[len("origin/") :])
    return names


def pending_commits(repo_dir: Path, from_branch: str, to_branch: str) -> list[Commit]:
    """Return commits present in `from_branch` but missing from `to_branch`."""

    result = run_git(
        repo_dir,
        [
            "log",
            f"origin/{to_branch}..origin/{from_branch}",
            f"--pretty=format:%H{COMMIT_SEP}%h{COMMIT_SEP}%an{COMMIT_SEP}%ad"
            f"{COMMIT_SEP}%T{COMMIT_SEP}%P{COMMIT_SEP}%s",
            "--date=iso-strict",
        ],
    )
    commits: list[Commit] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        parts = line.split(COMMIT_SEP, 6)
        if len(parts) != 7:
            commits.append({"raw": line})
            continue
        full, short, author, date, tree, parents_raw, subject = parts
        commits.append(
            {
                "hash": full,
                "short_hash": short,
                "author": author,
                "date": date,
                "tree": tree,
                "parents": parents_raw.split() if parents_raw else [],
                "subject": subject,
            }
        )
    return commits


def single_git_object_hash(stdout: str) -> str | None:
    """Parse one Git object hash from command output."""

    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        return None
    value = lines[0]
    return value if GIT_OBJECT_RE.fullmatch(value) is not None else None


def git_tree_hash(repo_dir: Path, ref: str) -> str | None:
    """Return one ref's tree hash, or None when Git cannot verify it."""

    result = run_git(repo_dir, ["rev-parse", f"{ref}^{{tree}}"], check=False)
    if result.returncode != 0:
        return None
    return single_git_object_hash(result.stdout)


def simulated_merge_tree_hash(repo_dir: Path, from_branch: str, to_branch: str) -> str | None:
    """Return the simulated source-into-target merge tree, or None on failure."""

    result = run_git(
        repo_dir,
        [
            "merge-tree",
            "--write-tree",
            f"origin/{to_branch}",
            f"origin/{from_branch}",
        ],
        check=False,
    )
    if result.returncode != 0:
        return None
    return single_git_object_hash(result.stdout)


def branch_pair_has_no_effective_file_change(repo_dir: Path, from_branch: str, to_branch: str) -> bool:
    """Return whether merging source into target would leave target's tree unchanged."""

    target_tree = git_tree_hash(repo_dir, f"origin/{to_branch}")
    if target_tree is None:
        return False
    merge_tree = simulated_merge_tree_hash(repo_dir, from_branch, to_branch)
    return merge_tree is not None and merge_tree == target_tree


def split_material_and_ignored_commits(
    repo_dir: Path,
    commits: list[Commit],
    ignore_non_material_commits: bool,
    from_branch: str,
    to_branch: str,
) -> tuple[list[Commit], list[Commit]]:
    """Split pending commits using branch-pair no-op merge simulation."""

    if not ignore_non_material_commits or not commits:
        return commits, []

    if branch_pair_has_no_effective_file_change(repo_dir, from_branch, to_branch):
        return [], commits
    return commits, []


def add_commit_drift_finding(
    findings: list[Finding],
    check: CheckName,
    repo_url: str,
    repo_name: str,
    from_branch: str,
    to_branch: str,
    commits: list[Commit],
) -> None:
    """Append a commit-drift finding when the commit list is non-empty."""

    if not commits:
        return
    count = len(commits)
    findings.append(
        {
            "type": "commit_drift",
            "check": check,
            "repository": repo_name,
            "repository_url": repo_url,
            "from_branch": from_branch,
            "to_branch": to_branch,
            "commit_count": count,
            "commits": commits,
            "message": f"{to_branch} is missing {count} {commit_count_label(count)} from {from_branch}",
        }
    )


def add_ignored_non_material_commit_group(
    ignored_groups: list[IgnoredCommitGroup],
    check: CheckName,
    repo_url: str,
    repo_name: str,
    from_branch: str,
    to_branch: str,
    commits: list[Commit],
) -> None:
    """Append ignored no-op merge drift for one branch pair."""

    if not commits:
        return
    count = len(commits)
    ignored_groups.append(
        {
            "check": check,
            "repository": repo_name,
            "repository_url": repo_url,
            "from_branch": from_branch,
            "to_branch": to_branch,
            "commit_count": count,
            "commits": commits,
            "message": (
                f"{to_branch} is missing {count} non-material "
                f"{commit_count_label(count)} from {from_branch}"
            ),
        }
    )


def add_repository_error_finding(
    findings: list[Finding],
    check: CheckName,
    repo_url: str,
    repo_name: str,
    message: str,
) -> None:
    """Append a repository-scoped operational error to an audit finding list."""

    findings.append(
        {
            "type": "repo_error",
            "check": check,
            "repository": repo_name,
            "repository_url": repo_url,
            "message": message,
        }
    )


def is_suppressed_branch(branch: str, suppressed_branches: set[str]) -> bool:
    """Return whether findings for a target branch should be suppressed."""

    return branch in suppressed_branches


def audit_repository(
    repo_url: str,
    repo_dir: Path,
    max_release_branches: int,
    ignore_non_material_commits: bool = False,
    suppressed_branches: Sequence[str] = (),
    logger: ProgressLogger | None = None,
) -> RepositoryReport:
    """Audit all branch containment invariants for a single repository."""

    repo_name = repo_display_name(repo_url)
    repo_result: RepositoryReport = {
        "repository": repo_name,
        "repository_url": repo_url,
        "status": "pass",
        "selected_branches": {"aws": [], "oci": []},
        "ignored_release_branches": [],
        "findings": [],
        "ignored_non_material_commits": [],
    }
    findings: list[Finding] = []
    ignored_groups: list[IgnoredCommitGroup] = []
    suppressed_branch_set = set(suppressed_branches)

    try:
        if logger:
            logger.info(f"Auditing repository {repo_name}")
            logger.debug(f"Repository URL: {repo_url}")
            logger.debug(f"Repository work directory: {repo_dir}")
        ensure_repo_fetched(repo_dir, repo_url)
        if logger:
            logger.debug(f"Fetched release branches for {repo_name}")
        branch_names = remote_release_branch_names(repo_dir)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        if logger:
            logger.error(f"Repository {repo_name} failed during fetch: {exc}")
        add_repository_error_finding(findings, "fetch", repo_url, repo_name, str(exc))
        repo_result["findings"] = findings
        repo_result["status"] = "fail"
        return repo_result

    parsed: list[ReleaseBranch] = []
    ignored: list[str] = []
    for name in branch_names:
        branch = parse_release_branch(name)
        if branch is None:
            ignored.append(name)
        else:
            parsed.append(branch)

    if logger:
        logger.debug(f"{repo_name}: found {len(branch_names)} remote release branch(es)")
        if ignored:
            logger.debug(f"{repo_name}: ignored {len(ignored)} release branch(es): {', '.join(ignored)}")

    aws_all = sort_newest_first(branch for branch in parsed if branch.major == AWS_MAJOR)
    oci_all = sort_newest_first(branch for branch in parsed if branch.major == OCI_MAJOR)
    aws_selected = select_newest(aws_all, max_release_branches)
    oci_selected = select_newest(oci_all, max_release_branches)
    oci_by_name = {branch.name: branch for branch in oci_all}

    repo_result["selected_branches"] = {
        "aws": [branch.name for branch in aws_selected],
        "oci": [branch.name for branch in oci_selected],
    }
    repo_result["ignored_release_branches"] = ignored

    if logger:
        logger.debug(
            f"{repo_name}: selected AWS branches: "
            + (", ".join(branch.name for branch in aws_selected) or "none")
        )
        logger.debug(
            f"{repo_name}: selected OCI branches: "
            + (", ".join(branch.name for branch in oci_selected) or "none")
        )

    try:
        for aws_branch in aws_selected:
            target_name = counterpart_oci_branch(aws_branch)
            if logger:
                logger.debug(f"{repo_name}: checking {target_name} contains {aws_branch.name}")
            if is_suppressed_branch(target_name, suppressed_branch_set):
                if logger:
                    logger.info(f"{repo_name}: suppressed drift check for {target_name}")
                continue
            if target_name not in oci_by_name:
                if logger:
                    logger.warn(f"{repo_name}: drift detected, {target_name} is missing")
                findings.append(
                    {
                        "type": "missing_branch",
                        "check": "aws_to_oci",
                        "repository": repo_name,
                        "repository_url": repo_url,
                        "from_branch": aws_branch.name,
                        "to_branch": target_name,
                        "message": f"{target_name} is missing for {aws_branch.name}",
                    }
                )
                continue
            commits = pending_commits(repo_dir, aws_branch.name, target_name)
            material_commits, ignored_commits = split_material_and_ignored_commits(
                repo_dir,
                commits,
                ignore_non_material_commits,
                aws_branch.name,
                target_name,
            )
            if logger and ignored_commits:
                count = len(ignored_commits)
                logger.info(
                    f"{repo_name}: ignored {count} non-material "
                    f"{commit_count_label(count)} missing from {aws_branch.name} into {target_name}"
                )
            if logger and material_commits:
                count = len(material_commits)
                logger.warn(
                    f"{repo_name}: {target_name} is missing "
                    f"{count} {commit_count_label(count)} from {aws_branch.name}"
                )
            add_commit_drift_finding(
                findings,
                "aws_to_oci",
                repo_url,
                repo_name,
                aws_branch.name,
                target_name,
                material_commits,
            )
            add_ignored_non_material_commit_group(
                ignored_groups,
                "aws_to_oci",
                repo_url,
                repo_name,
                aws_branch.name,
                target_name,
                ignored_commits,
            )

        adjacent_checks: tuple[tuple[CheckName, list[ReleaseBranch]], ...] = (
            ("aws_adjacent", aws_selected),
            ("oci_adjacent", oci_selected),
        )
        for family, branches in adjacent_checks:
            for newer, previous in zip(branches, branches[1:]):
                if logger:
                    logger.debug(f"{repo_name}: checking {newer.name} contains {previous.name} ({family})")
                if is_suppressed_branch(newer.name, suppressed_branch_set):
                    if logger:
                        logger.info(f"{repo_name}: suppressed drift check for {newer.name}")
                    continue
                commits = pending_commits(repo_dir, previous.name, newer.name)
                material_commits, ignored_commits = split_material_and_ignored_commits(
                    repo_dir,
                    commits,
                    ignore_non_material_commits,
                    previous.name,
                    newer.name,
                )
                if logger and ignored_commits:
                    count = len(ignored_commits)
                    logger.info(
                        f"{repo_name}: ignored {count} non-material "
                        f"{commit_count_label(count)} missing from {previous.name} into {newer.name}"
                    )
                if logger and material_commits:
                    count = len(material_commits)
                    logger.warn(
                        f"{repo_name}: {newer.name} is missing "
                        f"{count} {commit_count_label(count)} from {previous.name}"
                    )
                add_commit_drift_finding(
                    findings,
                    family,
                    repo_url,
                    repo_name,
                    previous.name,
                    newer.name,
                    material_commits,
                )
                add_ignored_non_material_commit_group(
                    ignored_groups,
                    family,
                    repo_url,
                    repo_name,
                    previous.name,
                    newer.name,
                    ignored_commits,
                )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        if logger:
            logger.error(f"Repository {repo_name} failed during drift checks: {exc}")
        add_repository_error_finding(findings, "drift", repo_url, repo_name, str(exc))

    repo_result["findings"] = findings
    repo_result["ignored_non_material_commits"] = ignored_groups
    if findings:
        repo_result["status"] = "fail"
        if logger:
            logger.warn(f"Repository {repo_name} failed with {len(findings)} finding(s)")
    elif logger:
        ignored_count = sum(group["commit_count"] for group in ignored_groups)
        if ignored_count:
            logger.info(f"Repository {repo_name} passed with {ignored_count} ignored non-material commit(s)")
        else:
            logger.info(f"Repository {repo_name} passed")
    return repo_result


def run_audit(
    config: RuntimeConfig,
    logger: ProgressLogger | None = None,
) -> AuditReport:
    """Run the drift audit for every configured repository."""

    repositories_to_scan = config["repositories"]
    work_dir = config["tmp_dir"]
    report: AuditReport = {
        "generated_at": utc_timestamp(),
        "status": "pass",
        "config": {
            "config_file": str(config["config_file"]),
            "tmp_dir": str(work_dir),
            "max_versions": config["max_versions"],
            "ignore_non_material_commits": config["ignore_non_material_commits"],
            "suppressed_branches": config["suppressed_branches"],
        },
        "repositories": [],
        "findings": [],
        "ignored_non_material_commits": [],
    }

    if shutil.which("git") is None:
        if logger:
            logger.error("git executable was not found on PATH")
        report["status"] = "fail"
        report["findings"] = [
            {
                "type": "config_error",
                "check": "git",
                "message": "git executable was not found on PATH",
            }
        ]
        return report

    try:
        work_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        if logger:
            logger.error(f"Could not create audit work directory {work_dir}: {exc}")
        report["status"] = "fail"
        report["findings"] = [
            {
                "type": "config_error",
                "check": "config",
                "message": f"Could not create audit work directory {work_dir}: {exc}",
            }
        ]
        return report
    if logger:
        repo_label = "repository" if len(repositories_to_scan) == 1 else "repositories"
        logger.info(f"Auditing {len(repositories_to_scan)} configured {repo_label}")
        logger.debug(f"Audit work directory: {work_dir}")
    repositories: list[RepositoryReport] = []
    findings: list[Finding] = []
    ignored_groups: list[IgnoredCommitGroup] = []
    for index, repo_url in enumerate(repositories_to_scan, start=1):
        repo_dir = repo_work_dir(work_dir, index, repo_url)
        if logger:
            logger.info(f"Repository {index}/{len(repositories_to_scan)}: {repo_display_name(repo_url)}")
        repo_result = audit_repository(
            repo_url=repo_url,
            repo_dir=repo_dir,
            max_release_branches=config["max_versions"],
            ignore_non_material_commits=config["ignore_non_material_commits"],
            suppressed_branches=config["suppressed_branches"],
            logger=logger,
        )
        repositories.append(repo_result)
        findings.extend(repo_result["findings"])
        ignored_groups.extend(repo_result["ignored_non_material_commits"])

    report["repositories"] = repositories
    report["findings"] = findings
    report["ignored_non_material_commits"] = ignored_groups
    if findings:
        report["status"] = "fail"
    if logger:
        logger.debug(f"Audit complete: status={report['status']}, findings={len(findings)}")
    return report


def commit_label(commit: Commit) -> str:
    """Render a commit as the short hash plus subject used in reports."""

    if "raw" in commit:
        return commit["raw"]
    full_hash = commit.get("hash", "")
    short_hash = full_hash[:8] if full_hash else commit.get("short_hash", "")
    return f"{short_hash} {commit.get('subject', '')}".strip()


def scanned_branches(report: AuditReport, family: BranchFamily) -> list[str]:
    """Return distinct scanned branches across repositories for a report header."""

    branch_names: list[str] = []
    seen: set[str] = set()
    suppressed = set(suppressed_branch_names(report))
    for repo in report["repositories"]:
        for name in repo["selected_branches"][family]:
            if name in suppressed:
                continue
            if name not in seen:
                branch_names.append(name)
                seen.add(name)

    parsed: list[ReleaseBranch] = []
    for name in branch_names:
        branch = parse_release_branch(name)
        if branch is None:
            return branch_names
        parsed.append(branch)
    return [branch.name for branch in sort_newest_first(parsed)]


def append_scanned_branch_section(lines: list[str], report: AuditReport) -> None:
    """Append the AWS/OCI branch summary section to a Markdown report."""

    lines.append("- Scanned branches")
    branch_families: tuple[tuple[str, BranchFamily], ...] = (("AWS", "aws"), ("OCI", "oci"))
    for label, family in branch_families:
        lines.append(f"  - {label}:")
        branches = scanned_branches(report, family)
        if branches:
            for branch in branches:
                lines.append(f"    - `{branch}`")
        else:
            lines.append("    - _none_")


def finding_repository_key(finding: Finding) -> str | None:
    """Return the stable grouping key for a repository finding."""

    repository_url = finding.get("repository_url")
    if isinstance(repository_url, str) and repository_url:
        return repository_url
    repository = finding.get("repository")
    return repository if isinstance(repository, str) else None


def report_repository_key(repo: RepositoryReport) -> str:
    """Return the stable grouping key for a repository report."""

    repository_url = repo.get("repository_url")
    if isinstance(repository_url, str) and repository_url:
        return repository_url
    return repo["repository"]


def grouped_findings_by_repo(report: AuditReport) -> list[tuple[RepositoryReport, list[Finding]]]:
    """Group findings by repository while preserving report repository order."""

    findings_by_repo: dict[str, list[Finding]] = {}
    for finding in report["findings"]:
        repository_key = finding_repository_key(finding)
        if repository_key is not None:
            findings_by_repo.setdefault(repository_key, []).append(finding)

    grouped: list[tuple[RepositoryReport, list[Finding]]] = []
    for repo in report["repositories"]:
        repository_key = report_repository_key(repo)
        if repository_key in findings_by_repo:
            grouped.append((repo, findings_by_repo.pop(repository_key)))

    for repository_key, findings in findings_by_repo.items():
        repository = finding_text(findings[0], "repository", repository_key)
        grouped.append(
            (
                {
                    "repository": repository,
                    "repository_url": "",
                    "status": "fail",
                    "selected_branches": {"aws": [], "oci": []},
                    "ignored_release_branches": [],
                    "findings": findings,
                    "ignored_non_material_commits": [],
                },
                findings,
            )
        )
    return grouped


def append_configuration_findings(lines: list[str], findings: list[Finding]) -> None:
    """Append non-repository findings, such as config or Git setup failures."""

    if not findings:
        return
    lines.extend(["## CONFIGURATION", ""])
    for finding in findings:
        check = finding.get("check", "unknown")
        lines.append(f"### `{check}`")
        lines.append("")
        lines.append(f"- Type: `{finding.get('type')}`")
        lines.append(f"- Message: {finding.get('message')}")
        lines.append("")


def finding_text(finding: Finding, key: str, default: str = "unknown") -> str:
    """Read a string field from a finding with a safe fallback."""

    value = finding.get(key)
    return value if isinstance(value, str) else default


def finding_commits(finding: Finding) -> list[Commit]:
    """Read commit entries from a finding with a safe fallback."""

    commits = finding.get("commits")
    return cast("list[Commit]", commits) if isinstance(commits, list) else []


def ignored_non_material_commit_groups(report: AuditReport) -> list[IgnoredCommitGroup]:
    """Read ignored commit groups from a report with a safe fallback."""

    groups = report.get("ignored_non_material_commits")
    return cast("list[IgnoredCommitGroup]", groups) if isinstance(groups, list) else []


def ignored_non_material_commit_count(report: AuditReport) -> int:
    """Return the number of non-material branch-pair drift commits ignored."""

    return sum(group["commit_count"] for group in ignored_non_material_commit_groups(report))


def ignore_non_material_commits_enabled(report: AuditReport) -> bool:
    """Return the report config's ignored-commit mode, defaulting to disabled."""

    config = report.get("config", {})
    if not isinstance(config, dict):
        return False
    return bool(config.get("ignore_non_material_commits", False))


def suppressed_branch_names(report: AuditReport) -> list[str]:
    """Return configured target branches whose findings are suppressed."""

    config = report.get("config", {})
    if not isinstance(config, dict):
        return []
    value = config.get("suppressed_branches", [])
    return cast("list[str]", value) if isinstance(value, list) else []


def append_repository_findings(lines: list[str], repo: RepositoryReport, findings: list[Finding]) -> None:
    """Append all drift details for one repository to a Markdown report."""

    lines.append(f"## REPOSITORY: `{repo['repository']}`")
    lines.append("")

    findings_by_target: dict[str, list[Finding]] = {}
    for finding in findings:
        target = finding_text(finding, "to_branch")
        findings_by_target.setdefault(target, []).append(finding)

    for target, target_findings in findings_by_target.items():
        lines.append(f"## DRIFT DETECTED IN BRANCH `{target}`")
        lines.append("")
        for finding in target_findings:
            source = finding_text(finding, "from_branch")
            commits = finding_commits(finding)
            if commits:
                count = int(finding.get("commit_count") or len(commits))
                lines.append(f"### Missing {count} {commit_count_label(count)} from `{source}`")
                lines.append("")
                for commit in commits:
                    lines.append(f"- `{commit_label(commit)}`")
                lines.append("")
            elif finding.get("type") == "missing_branch":
                lines.append(f"### Missing branch for `{source}`")
                lines.append("")
                lines.append(f"- {finding.get('message')}")
                lines.append("")
            else:
                lines.append(f"### `{finding_text(finding, 'check')}`")
                lines.append("")
                lines.append(f"- {finding.get('message')}")
        lines.append("")


def render_markdown(report: AuditReport) -> str:
    """Render the detailed Markdown report expected by Jenkins artifacts."""

    lines = [
        "# SFP Release Drift Report",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Status: `{report['status']}`",
    ]
    append_scanned_branch_section(lines, report)
    lines.append("")

    findings = report["findings"]
    if not findings:
        lines.append("No release-branch drift detected.")
        lines.append("")
        return "\n".join(lines)

    config_findings = [
        finding
        for finding in findings
        if not isinstance(finding.get("repository"), str)
    ]
    append_configuration_findings(lines, config_findings)

    for repo, repo_findings in grouped_findings_by_repo(report):
        append_repository_findings(lines, repo, repo_findings)
    return "\n".join(lines)


def render_slack_text(report: AuditReport, max_commits_per_finding: int) -> str:
    """Render a compact Slack alert summary for failed audits."""

    findings = report["findings"]
    if not findings:
        return "SFP release-branch drift audit passed."

    summary = f"SFP release-branch drift audit failed with {len(findings)} finding(s)."
    lines = [summary, ""]
    for finding in findings[:20]:
        repo = finding.get("repository", "configuration")
        check = finding.get("check", "unknown")
        lines.append(f"* {repo} [{check}]: {finding.get('message')}")
        commits = finding_commits(finding)
        if commits:
            shown = commits[:max_commits_per_finding]
            for commit in shown:
                lines.append(f"  - {commit_label(commit)}")
            hidden = len(commits) - len(shown)
            if hidden > 0:
                lines.append(f"  - ... {hidden} more {commit_count_label(hidden)} in archived report")
    hidden_findings = len(findings) - 20
    if hidden_findings > 0:
        lines.append(f"* ... {hidden_findings} more finding(s) in archived report")
    return "\n".join(lines)


def has_branch_drift(repo: RepositoryReport) -> bool:
    """Return whether a repository has branch containment drift findings."""

    return any(
        finding.get("type") in {"commit_drift", "missing_branch"}
        for finding in repo["findings"]
    )


def branch_drift_repository_count(report: AuditReport) -> int:
    """Count repositories with at least one missing branch or missing commit."""

    return sum(1 for repo in report["repositories"] if has_branch_drift(repo))


def log_completion_summary(report: AuditReport, logger: ProgressLogger) -> None:
    """Log the final human-readable audit summary."""

    drift_repo_count = branch_drift_repository_count(report)
    scanned_repo_count = len(report["repositories"])
    finding_count = len(report["findings"])
    if report["status"] == "fail":
        if drift_repo_count:
            logger.error(
                "Drift analysis complete: found "
                f"{drift_repo_count} repositories with at least one branch missing commits"
            )
        else:
            logger.error(f"Drift analysis failed before finding branch drift: {finding_count} finding(s)")
    else:
        logger.info(
            "Drift analysis complete: no missing commits found in "
            f"{scanned_repo_count} repositories scanned"
        )


def write_reports(
    report: AuditReport,
    report_md: Path | None,
    slack_text: Path | None,
    logger: ProgressLogger | None = None,
) -> None:
    """Write configured report artifacts, or Markdown to stdout without one."""

    markdown = render_markdown(report)
    if report_md is not None:
        report_md.parent.mkdir(parents=True, exist_ok=True)
        report_md.write_text(markdown, encoding="utf-8")
        if logger:
            logger.info(f"Wrote Markdown report to {report_md}")
    if slack_text is not None:
        slack_text.parent.mkdir(parents=True, exist_ok=True)
        slack_text.write_text(render_slack_text(report, DEFAULT_MAX_COMMITS_PER_FINDING), encoding="utf-8")
        if logger:
            logger.info(f"Wrote Slack text to {slack_text}")
    if report_md is None:
        if logger:
            logger.info("Writing Markdown report to stdout")
        print(markdown)


def main(argv: Sequence[str]) -> int:
    """CLI entry point. Return 0 for clean audits and 1 for drift/config failures."""

    args = parse_args(argv)
    logger = ProgressLogger()
    logger.info("Starting SFP release-branch drift audit")
    config_file = args.config
    try:
        config = load_config(config_file)
    except ConfigError as exc:
        logger.error(str(exc))
        report = config_error_report(config_file, str(exc))
        write_reports(report=report, report_md=None, slack_text=None, logger=logger)
        log_completion_summary(report, logger)
        return 1

    logger.verbose = config["verbose"]
    logger.info(f"Loaded config from {config['config_file']}")
    report = run_audit(config=config, logger=logger)
    write_reports(
        report=report,
        report_md=config["output_report_file"],
        slack_text=config["slack_text_file"],
        logger=logger,
    )
    exit_code = 0 if report["status"] == "pass" else 1
    log_completion_summary(report, logger)
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
