#!/usr/bin/env python3
"""Falcon Jenkins build helper for Codex sessions.

The script intentionally avoids third-party dependencies and never prints the
token value. It is designed for API reads, evidence collection under /tmp, and
fixture-based tests.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_BASE_URL = "https://hed.sfp.ocs.oc-test.com/falcon"
DEFAULT_TOKEN_ENV = "FALCON_JENKINS_TOKEN"
EVIDENCE_ROOT = Path("/tmp/orange-jenkins-build-guardian")
SHA_RE = re.compile(r"\b[0-9a-fA-F]{40}\b")


class JenkinsError(RuntimeError):
    pass


@dataclass(frozen=True)
class NormalizedTarget:
    base_url: str
    job_name: str
    job_segments: list[str]
    job_url: str
    build: int | None = None
    build_url: str | None = None


@dataclass(frozen=True)
class ProgressiveText:
    text: str
    start: int
    next_start: int
    more_data: bool


def strip_trailing_slash(value: str) -> str:
    return value.rstrip("/")


def decode_jenkins_segment(segment: str) -> str:
    current = segment
    for _ in range(3):
        decoded = urllib.parse.unquote(current)
        if decoded == current:
            return decoded
        current = decoded
    return current


def encode_jenkins_segment(segment: str) -> str:
    return urllib.parse.quote(segment, safe="")


def join_url_path(base_url: str, path: str) -> str:
    base = strip_trailing_slash(base_url)
    return f"{base}/{path.lstrip('/')}"


def job_name_to_url(base_url: str, job_name: str) -> tuple[str, list[str], str]:
    raw = job_name.strip().strip("/")
    if not raw:
        raise JenkinsError("job name is empty")

    if raw.startswith("job/") or "/job/" in raw:
        parts = [part for part in raw.split("/") if part]
        segments: list[str] = []
        index = 0
        while index < len(parts):
            if parts[index] != "job" or index + 1 >= len(parts):
                raise JenkinsError(
                    "job-name paths containing '/job/' must use Jenkins '/job/<segment>' pairs"
                )
            segments.append(decode_jenkins_segment(parts[index + 1]))
            index += 2
    else:
        segments = [decode_jenkins_segment(part) for part in raw.split("/") if part]

    encoded = "/".join(f"job/{encode_jenkins_segment(segment)}" for segment in segments)
    return "/".join(segments), segments, join_url_path(base_url, encoded)


def parse_jenkins_url(url: str, fallback_base_url: str) -> NormalizedTarget:
    parsed = urllib.parse.urlsplit(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise JenkinsError(f"not an absolute Jenkins URL: {url}")

    parts = [part for part in parsed.path.split("/") if part]
    job_segments_raw: list[str] = []
    job_path_parts: list[str] = []
    build: int | None = None
    index = 0
    last_job_part_index = -1

    while index < len(parts):
        part = parts[index]
        if part == "job" and index + 1 < len(parts):
            job_path_parts.extend([parts[index], parts[index + 1]])
            job_segments_raw.append(parts[index + 1])
            last_job_part_index = index + 1
            index += 2
            continue
        index += 1

    if not job_segments_raw:
        raise JenkinsError(f"could not find '/job/<name>' segments in URL: {url}")

    if last_job_part_index + 1 < len(parts) and parts[last_job_part_index + 1].isdigit():
        build = int(parts[last_job_part_index + 1])

    # Recompute base path as everything before the first /job/ segment.
    first_job_index = parts.index("job")
    base_path = "/" + "/".join(parts[:first_job_index]) if first_job_index > 0 else ""
    base_url = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, base_path.rstrip("/"), "", "")
    )
    if not base_url.rstrip("/"):
        base_url = fallback_base_url

    job_path = "/" + "/".join(job_path_parts)
    job_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, f"{base_path}{job_path}", "", ""))
    job_url = strip_trailing_slash(job_url)
    build_url = f"{job_url}/{build}" if build is not None else None
    segments = [decode_jenkins_segment(segment) for segment in job_segments_raw]
    return NormalizedTarget(
        base_url=strip_trailing_slash(base_url),
        job_name="/".join(segments),
        job_segments=segments,
        job_url=job_url,
        build=build,
        build_url=build_url,
    )


def normalize_target(args: argparse.Namespace) -> NormalizedTarget:
    base_url = strip_trailing_slash(args.base_url)
    if args.job_url:
        normalized = parse_jenkins_url(args.job_url, base_url)
        if args.build is not None:
            normalized = NormalizedTarget(
                base_url=normalized.base_url,
                job_name=normalized.job_name,
                job_segments=normalized.job_segments,
                job_url=normalized.job_url,
                build=args.build,
                build_url=f"{normalized.job_url}/{args.build}",
            )
        return normalized

    if not args.job_name:
        raise JenkinsError("provide --job-url or --job-name")
    job_name, segments, job_url = job_name_to_url(base_url, args.job_name)
    build = args.build
    return NormalizedTarget(
        base_url=base_url,
        job_name=job_name,
        job_segments=segments,
        job_url=job_url,
        build=build,
        build_url=f"{job_url}/{build}" if build is not None else None,
    )


def api_json_url(url: str) -> str:
    clean = strip_trailing_slash(url)
    if clean.endswith("/api/json"):
        return clean
    return f"{clean}/api/json"


class JenkinsClient:
    def __init__(self, username: str | None, token_env: str, timeout: int = 30) -> None:
        self.username = username
        self.token_env = token_env
        self.timeout = timeout
        self._token = os.environ.get(token_env)

    def require_auth(self) -> None:
        if not self.username:
            raise JenkinsError("Jenkins username is required; pass --username with Oracle email")
        if not self._token:
            raise JenkinsError(f"Jenkins token environment variable is not set: {self.token_env}")

    def _headers(self) -> dict[str, str]:
        headers = {"User-Agent": "codex-orange-jenkins-build-guardian/1.0"}
        if self.username or self._token:
            self.require_auth()
            raw = f"{self.username}:{self._token}".encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        return headers

    def request(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        binary: bool = False,
    ) -> tuple[bytes, dict[str, str]]:
        if params:
            query = urllib.parse.urlencode(params)
            separator = "&" if urllib.parse.urlsplit(url).query else "?"
            url = f"{url}{separator}{query}"
        request = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = response.read()
                headers = {key.lower(): value for key, value in response.headers.items()}
                return data, headers
        except urllib.error.HTTPError as exc:
            raise JenkinsError(f"Jenkins HTTP {exc.code} for {redact_url(url)}") from exc
        except urllib.error.URLError as exc:
            raise JenkinsError(f"Jenkins network error for {redact_url(url)}: {exc.reason}") from exc

    def get_json(self, url: str, tree: str | None = None) -> dict[str, Any]:
        params = {"tree": tree} if tree else None
        data, _ = self.request(api_json_url(url), params=params)
        try:
            return json.loads(data.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise JenkinsError(f"Jenkins returned non-JSON for {redact_url(url)}") from exc

    def get_text(self, url: str, params: dict[str, Any] | None = None) -> tuple[str, dict[str, str]]:
        data, headers = self.request(url, params=params)
        return data.decode("utf-8", errors="replace"), headers

    def get_binary(self, url: str) -> bytes:
        data, _ = self.request(url, binary=True)
        return data


def make_client(args: argparse.Namespace, *, require_auth: bool = True) -> JenkinsClient:
    client = JenkinsClient(args.username, args.token_env, timeout=args.timeout)
    if require_auth:
        client.require_auth()
    return client


def redact_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def resolve_latest_build(client: JenkinsClient, target: NormalizedTarget) -> dict[str, Any]:
    job_json = client.get_json(
        target.job_url,
        tree="name,url,lastBuild[number,url,result,building,timestamp,duration]",
    )
    latest = job_json.get("lastBuild")
    if not latest:
        raise JenkinsError(f"job has no lastBuild: {target.job_url}")
    return {"job": job_json, "latest": latest}


def with_resolved_build(client: JenkinsClient, target: NormalizedTarget) -> tuple[NormalizedTarget, dict[str, Any] | None]:
    if target.build is not None and target.build_url:
        return target, None
    latest = resolve_latest_build(client, target)
    number = latest["latest"].get("number")
    url = latest["latest"].get("url")
    if number is None:
        raise JenkinsError("latest build did not include a build number")
    return (
        NormalizedTarget(
            base_url=target.base_url,
            job_name=target.job_name,
            job_segments=target.job_segments,
            job_url=target.job_url,
            build=int(number),
            build_url=strip_trailing_slash(url) if url else f"{target.job_url}/{number}",
        ),
        latest,
    )


def progressive_console(client: JenkinsClient, build_url: str, start: int = 0) -> ProgressiveText:
    text, headers = client.get_text(
        f"{strip_trailing_slash(build_url)}/logText/progressiveText",
        params={"start": start},
    )
    next_start = int(headers.get("x-text-size", start + len(text.encode("utf-8"))))
    more_data = headers.get("x-more-data", "false").lower() == "true"
    return ProgressiveText(text=text, start=start, next_start=next_start, more_data=more_data)


def read_full_console(
    client: JenkinsClient,
    build_url: str,
    *,
    limit_bytes: int | None = None,
    sleep_seconds: float = 0.0,
) -> str:
    chunks: list[str] = []
    start = 0
    while True:
        chunk = progressive_console(client, build_url, start)
        chunks.append(chunk.text)
        previous_start = start
        start = chunk.next_start
        if limit_bytes is not None and start >= limit_bytes:
            break
        if not chunk.more_data:
            break
        if start == previous_start and not chunk.text:
            break
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return "".join(chunks)


def iter_json_values(data: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], Any]]:
    if isinstance(data, dict):
        for key, value in data.items():
            yield from iter_json_values(value, (*path, str(key)))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            yield from iter_json_values(value, (*path, str(index)))
    else:
        yield path, data


def action_parameters(build_json: dict[str, Any]) -> dict[str, str]:
    params: dict[str, str] = {}
    for action in build_json.get("actions") or []:
        if not isinstance(action, dict):
            continue
        for parameter in action.get("parameters") or []:
            if not isinstance(parameter, dict):
                continue
            name = parameter.get("name")
            value = parameter.get("value")
            if name is not None and value is not None:
                params[str(name)] = str(value)
    return params


def normalize_branch(branch: str) -> str:
    value = branch.strip()
    for prefix in ("origin/", "refs/heads/", "*/"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    return value


def extract_branch_sha(
    build_json: dict[str, Any],
    *,
    console_text: str = "",
    job_segments: list[str] | None = None,
) -> dict[str, Any]:
    params = action_parameters(build_json)
    branch_candidates: list[dict[str, str]] = []
    sha_candidates: list[dict[str, str]] = []

    branch_keys = {
        "BRANCH_NAME",
        "GIT_BRANCH",
        "CHANGE_BRANCH",
        "ghprbSourceBranch",
        "GERRIT_BRANCH",
        "BRANCH",
    }
    sha_keys = {
        "GIT_COMMIT",
        "COMMIT_SHA",
        "BUILD_VCS_NUMBER",
        "ghprbActualCommit",
        "GERRIT_PATCHSET_REVISION",
        "PULL_REQUEST_SHA",
    }

    for key, value in params.items():
        if key in branch_keys and value:
            branch_candidates.append({"source": f"parameter:{key}", "value": normalize_branch(value)})
        if key in sha_keys and SHA_RE.fullmatch(value):
            sha_candidates.append({"source": f"parameter:{key}", "value": value.lower()})

    for path, value in iter_json_values(build_json):
        if not isinstance(value, str):
            continue
        key = path[-1] if path else ""
        if key in branch_keys and value:
            branch_candidates.append({"source": ".".join(path), "value": normalize_branch(value)})
        if key in sha_keys and SHA_RE.fullmatch(value):
            sha_candidates.append({"source": ".".join(path), "value": value.lower()})
        if key.lower() in {"sha1", "commitid", "revision"} and SHA_RE.fullmatch(value):
            sha_candidates.append({"source": ".".join(path), "value": value.lower()})

    for item in ((build_json.get("changeSet") or {}).get("items") or []):
        if isinstance(item, dict):
            commit_id = item.get("commitId")
            if isinstance(commit_id, str) and SHA_RE.fullmatch(commit_id):
                sha_candidates.append({"source": "changeSet.items.commitId", "value": commit_id.lower()})

    for match in re.finditer(
        r"Checking out Revision\s+([0-9a-fA-F]{40})(?:\s+\((?:origin/)?([^)]+)\))?",
        console_text,
    ):
        sha_candidates.append({"source": "console:Checking out Revision", "value": match.group(1).lower()})
        if match.group(2):
            branch_candidates.append(
                {"source": "console:Checking out Revision", "value": normalize_branch(match.group(2))}
            )

    for match in re.finditer(r"Branch(?:es)? Specifier.*?[:=]\s+(?:origin/|\*/)?([^\s]+)", console_text):
        branch_candidates.append({"source": "console:Branch Specifier", "value": normalize_branch(match.group(1))})

    for match in SHA_RE.finditer(console_text):
        sha_candidates.append({"source": "console:first-sha", "value": match.group(0).lower()})
        break

    if job_segments:
        last_segment = normalize_branch(job_segments[-1])
        if last_segment and last_segment.lower() not in {"master", "main", "develop", "trunk"}:
            branch_candidates.append({"source": "job-url:last-segment", "value": last_segment})

    branch_candidates = dedupe_candidates(branch_candidates)
    sha_candidates = dedupe_candidates(sha_candidates)
    return {
        "branch": branch_candidates[0]["value"] if branch_candidates else None,
        "sha": sha_candidates[0]["value"] if sha_candidates else None,
        "branch_candidates": branch_candidates[:10],
        "sha_candidates": sha_candidates[:10],
    }


def dedupe_candidates(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for candidate in candidates:
        key = (candidate.get("source", ""), candidate.get("value", ""))
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def concise_status(build_json: dict[str, Any], branch_info: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "number": build_json.get("number"),
        "url": strip_trailing_slash(str(build_json.get("url") or "")) or None,
        "building": bool(build_json.get("building")),
        "result": build_json.get("result"),
        "timestamp": build_json.get("timestamp"),
        "duration": build_json.get("duration"),
        "estimatedDuration": build_json.get("estimatedDuration"),
        "fullDisplayName": build_json.get("fullDisplayName"),
    }
    if branch_info:
        result["branch"] = branch_info.get("branch")
        result["sha"] = branch_info.get("sha")
    return result


def collect_test_failures(test_report: dict[str, Any] | None) -> list[str]:
    if not test_report:
        return []
    failures: list[str] = []
    for suite in test_report.get("suites") or []:
        if not isinstance(suite, dict):
            continue
        for case in suite.get("cases") or []:
            if not isinstance(case, dict):
                continue
            status = str(case.get("status") or "").upper()
            if status in {"FAILED", "REGRESSION", "ERROR"} or case.get("errorDetails"):
                class_name = case.get("className") or suite.get("name") or "<unknown>"
                name = case.get("name") or "<unknown>"
                details = str(case.get("errorDetails") or "").strip().splitlines()
                detail = f": {details[0]}" if details else ""
                failures.append(f"{class_name}.{name}{detail}")
    return failures


CLASSIFIERS: list[tuple[str, str, list[str]]] = [
    (
        "mockito_matcher_misuse",
        "test_failure",
        [
            "InvalidUseOfMatchersException",
            "Misplaced or misused argument matcher",
            "matchers expected",
        ],
    ),
    ("maven_compilation", "compilation", ["COMPILATION ERROR", "Compilation failure", "cannot find symbol"]),
    ("maven_dependency", "dependency_resolution", ["Could not resolve dependencies", "Could not transfer artifact"]),
    ("surefire_tests", "test_failure", ["There are test failures", "Failed tests:", "Surefire report"]),
    ("junit_tests", "test_failure", ["Tests run:", "Failures:", "Errors:"]),
    ("checker_or_static_analysis", "static_analysis", ["Checker Framework", "SpotBugs", "Checkstyle", "PMD"]),
    ("timeout", "timeout", ["Timeout has been exceeded", "Cancelling nested steps due to timeout", "timed out"]),
    ("agent_infra", "infrastructure", ["Agent went offline", "Cannot contact", "No space left on device", "channel is already closed"]),
    ("scm_checkout", "scm", ["Couldn't find any revision", "git fetch", "fatal: unable to access", "hudson.plugins.git"]),
    ("auth", "auth", ["HTTP 401", "HTTP 403", "permission denied", "AccessDeniedException"]),
]


def classify_failure(console_text: str, test_report: dict[str, Any] | None = None) -> dict[str, Any]:
    signatures: list[dict[str, str]] = []
    failure_type = "unknown"

    test_failures = collect_test_failures(test_report)
    for failure in test_failures[:10]:
        signatures.append({"kind": "test_report", "text": failure})
    if test_failures:
        failure_type = "test_failure"

    for name, classifier_type, needles in CLASSIFIERS:
        matched = [needle for needle in needles if needle.lower() in console_text.lower()]
        if matched:
            signatures.append({"kind": name, "text": ", ".join(matched)})
            if failure_type == "unknown" or name == "mockito_matcher_misuse":
                failure_type = classifier_type

    for line in interesting_console_lines(console_text):
        signatures.append({"kind": "console", "text": line})
        if len(signatures) >= 15:
            break

    likely_environmental = failure_type in {"infrastructure", "dependency_resolution", "timeout", "scm", "auth"}
    return {
        "failure_type": failure_type,
        "likely_environmental": likely_environmental,
        "signature_count": len(signatures),
        "top_signatures": signatures[:15],
    }


def interesting_console_lines(console_text: str) -> list[str]:
    patterns = [
        re.compile(r"\[ERROR\].+"),
        re.compile(r".*Exception[: ].*"),
        re.compile(r".*AssertionError.*"),
        re.compile(r".*FAILURE.*"),
        re.compile(r".*Failed tests?:.*"),
    ]
    result: list[str] = []
    seen: set[str] = set()
    for raw_line in console_text.splitlines():
        line = raw_line.strip()
        if not line or len(line) > 300:
            continue
        if any(pattern.match(line) for pattern in patterns):
            if line not in seen:
                seen.add(line)
                result.append(line)
        if len(result) >= 20:
            break
    return result


def fetch_test_report(client: JenkinsClient, build_url: str) -> dict[str, Any] | None:
    try:
        return client.get_json(
            f"{strip_trailing_slash(build_url)}/testReport",
            tree="failCount,skipCount,totalCount,suites[name,cases[className,name,status,errorDetails,errorStackTrace]]",
        )
    except JenkinsError:
        return None


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned[:120] or "jenkins-build"


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def safe_artifact_path(root: Path, relative_path: str) -> Path:
    target = root / relative_path
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    if resolved_root not in resolved_target.parents and resolved_target != resolved_root:
        raise JenkinsError(f"unsafe artifact path from Jenkins: {relative_path}")
    return resolved_target


def cmd_normalize(args: argparse.Namespace) -> dict[str, Any]:
    return asdict(normalize_target(args))


def cmd_latest(args: argparse.Namespace) -> dict[str, Any]:
    target = normalize_target(args)
    client = make_client(args)
    latest = resolve_latest_build(client, target)
    return {"target": asdict(target), **latest}


def cmd_status(args: argparse.Namespace) -> dict[str, Any]:
    target = normalize_target(args)
    client = make_client(args)
    target, latest = with_resolved_build(client, target)
    build_json = client.get_json(
        target.build_url,
        tree=(
            "number,url,result,building,timestamp,duration,estimatedDuration,fullDisplayName,"
            "actions[parameters[name,value],lastBuiltRevision[SHA1,branch[name]]],"
            "changeSet[items[commitId,msg,author[fullName]]]"
        ),
    )
    branch_info = extract_branch_sha(build_json, job_segments=target.job_segments)
    return {
        "target": asdict(target),
        "latest": latest,
        "status": concise_status(build_json, branch_info),
        "branch_info": branch_info,
    }


def cmd_wait(args: argparse.Namespace) -> dict[str, Any]:
    target = normalize_target(args)
    client = make_client(args)
    target, latest = with_resolved_build(client, target)
    start_time = time.time()
    interval = args.interval
    console_start = 0
    polls = 0
    last_build_json: dict[str, Any] | None = None

    while True:
        polls += 1
        last_build_json = client.get_json(
            target.build_url,
            tree="number,url,result,building,timestamp,duration,estimatedDuration,fullDisplayName,actions[parameters[name,value]],changeSet[items[commitId]]",
        )
        try:
            chunk = progressive_console(client, target.build_url, console_start)
            console_start = chunk.next_start
        except JenkinsError:
            pass
        if not last_build_json.get("building"):
            break
        if args.max_wait_seconds is not None and time.time() - start_time >= args.max_wait_seconds:
            raise JenkinsError(f"build still running after {args.max_wait_seconds} seconds")
        time.sleep(interval)
        interval = min(args.max_interval, max(interval + 5, int(interval * 1.5)))

    branch_info = extract_branch_sha(last_build_json, job_segments=target.job_segments)
    return {
        "target": asdict(target),
        "latest": latest,
        "polls": polls,
        "elapsed_seconds": round(time.time() - start_time, 3),
        "console_bytes_read": console_start,
        "status": concise_status(last_build_json, branch_info),
        "branch_info": branch_info,
    }


def cmd_tail(args: argparse.Namespace) -> dict[str, Any]:
    target = normalize_target(args)
    client = make_client(args)
    target, latest = with_resolved_build(client, target)
    chunk = progressive_console(client, target.build_url, args.start)
    return {"target": asdict(target), "latest": latest, "tail": asdict(chunk)}


def cmd_download_failure(args: argparse.Namespace) -> dict[str, Any]:
    target = normalize_target(args)
    client = make_client(args)
    target, latest = with_resolved_build(client, target)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    case_dir = EVIDENCE_ROOT / f"{safe_name(target.job_name)}-{target.build}-{stamp}"
    artifact_dir = case_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=False)

    job_json = client.get_json(
        target.job_url,
        tree="name,url,lastBuild[number,url,result,building],builds[number,url,result,building]{0,10}",
    )
    build_json = client.get_json(
        target.build_url,
        tree=(
            "number,url,result,building,timestamp,duration,estimatedDuration,fullDisplayName,"
            "actions[parameters[name,value],lastBuiltRevision[SHA1,branch[name]]],"
            "changeSet[items[commitId,msg,author[fullName]]],"
            "artifacts[fileName,relativePath]"
        ),
    )
    test_report = fetch_test_report(client, target.build_url)
    console_text = read_full_console(client, target.build_url, limit_bytes=args.console_limit_bytes)

    write_json(case_dir / "target.json", asdict(target))
    write_json(case_dir / "job.json", job_json)
    write_json(case_dir / "build.json", build_json)
    if latest:
        write_json(case_dir / "latest.json", latest)
    if test_report is not None:
        write_json(case_dir / "test_report.json", test_report)
    (case_dir / "console.txt").write_text(console_text, encoding="utf-8")

    artifact_results: list[dict[str, Any]] = []
    artifacts = build_json.get("artifacts") or []
    for artifact in artifacts[: args.max_artifacts]:
        if not isinstance(artifact, dict) or not artifact.get("relativePath"):
            continue
        relative_path = str(artifact["relativePath"])
        artifact_url = f"{strip_trailing_slash(target.build_url)}/artifact/{urllib.parse.quote(relative_path, safe='/')}"
        try:
            data = client.get_binary(artifact_url)
            output_path = safe_artifact_path(artifact_dir, relative_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(data)
            artifact_results.append(
                {"relativePath": relative_path, "bytes": len(data), "path": str(output_path)}
            )
        except JenkinsError as exc:
            artifact_results.append({"relativePath": relative_path, "error": str(exc)})

    write_json(case_dir / "artifacts_index.json", artifact_results)
    classification = classify_failure(console_text, test_report)
    write_json(case_dir / "classification.json", classification)
    return {
        "target": asdict(target),
        "latest": latest,
        "evidence_dir": str(case_dir),
        "files": sorted(path.name for path in case_dir.iterdir()),
        "artifact_count": len(artifact_results),
        "classification": classification,
    }


def cmd_branch_info(args: argparse.Namespace) -> dict[str, Any]:
    target = normalize_target(args)
    client = make_client(args)
    target, latest = with_resolved_build(client, target)
    build_json = client.get_json(
        target.build_url,
        tree=(
            "number,url,result,building,actions[parameters[name,value],lastBuiltRevision[SHA1,branch[name]]],"
            "changeSet[items[commitId,msg,author[fullName]]]"
        ),
    )
    console_text = ""
    if args.include_console:
        console_text = read_full_console(client, target.build_url, limit_bytes=args.console_limit_bytes)
    branch_info = extract_branch_sha(
        build_json,
        console_text=console_text,
        job_segments=target.job_segments,
    )
    return {"target": asdict(target), "latest": latest, "branch_info": branch_info}


def cmd_classify(args: argparse.Namespace) -> dict[str, Any]:
    if args.evidence_dir:
        evidence_dir = Path(args.evidence_dir)
        if not evidence_dir.is_dir():
            raise JenkinsError(f"evidence directory does not exist: {evidence_dir}")
        console_path = evidence_dir / "console.txt"
        report_path = evidence_dir / "test_report.json"
        console_text = console_path.read_text(encoding="utf-8") if console_path.exists() else ""
        test_report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.exists() else None
        return {
            "evidence_dir": str(evidence_dir),
            "classification": classify_failure(console_text, test_report),
        }

    target = normalize_target(args)
    client = make_client(args)
    target, latest = with_resolved_build(client, target)
    test_report = fetch_test_report(client, target.build_url)
    console_text = read_full_console(client, target.build_url, limit_bytes=args.console_limit_bytes)
    return {
        "target": asdict(target),
        "latest": latest,
        "classification": classify_failure(console_text, test_report),
    }


def emit(data: Any, args: argparse.Namespace) -> None:
    indent = 2 if args.json else None
    print(json.dumps(data, indent=indent, sort_keys=bool(args.json)))


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--job-url", help="Jenkins job URL or build URL")
    parser.add_argument("--job-name", help="Jenkins job name, slash-separated folder path, or /job/<name> path")
    parser.add_argument("--build", type=int, help="Jenkins build number")
    parser.add_argument("--username", help="Oracle email / Jenkins username")
    parser.add_argument("--token-env", default=DEFAULT_TOKEN_ENV, help="Environment variable containing Jenkins token")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Falcon Jenkins base URL")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Pretty-print JSON output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Orange/Falcon Jenkins build helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("normalize", "latest", "status", "wait", "tail", "download-failure", "branch-info", "classify"):
        sub = subparsers.add_parser(name)
        add_common_arguments(sub)

    wait = subparsers.choices["wait"]
    wait.add_argument("--interval", type=int, default=10, help="Initial polling interval in seconds")
    wait.add_argument("--max-interval", type=int, default=60, help="Maximum polling interval in seconds")
    wait.add_argument("--max-wait-seconds", type=int, help="Abort after this many seconds")

    tail = subparsers.choices["tail"]
    tail.add_argument("--start", type=int, default=0, help="Progressive console byte offset")

    download = subparsers.choices["download-failure"]
    download.add_argument("--max-artifacts", type=int, default=20, help="Maximum artifacts to download")
    download.add_argument("--console-limit-bytes", type=int, help="Maximum console bytes to read")

    branch = subparsers.choices["branch-info"]
    branch.add_argument("--include-console", action="store_true", help="Read console text for extra branch/SHA hints")
    branch.add_argument("--console-limit-bytes", type=int, default=200_000, help="Maximum console bytes to read")

    classify = subparsers.choices["classify"]
    classify.add_argument("--evidence-dir", help="Evidence directory produced by download-failure")
    classify.add_argument("--console-limit-bytes", type=int, default=500_000, help="Maximum console bytes to read")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    commands = {
        "normalize": cmd_normalize,
        "latest": cmd_latest,
        "status": cmd_status,
        "wait": cmd_wait,
        "tail": cmd_tail,
        "download-failure": cmd_download_failure,
        "branch-info": cmd_branch_info,
        "classify": cmd_classify,
    }
    try:
        emit(commands[args.command](args), args)
        return 0
    except JenkinsError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
