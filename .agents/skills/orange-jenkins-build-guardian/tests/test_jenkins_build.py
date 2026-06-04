import argparse
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "jenkins_build.py"
SPEC = importlib.util.spec_from_file_location("jenkins_build", SCRIPT)
jenkins_build = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["jenkins_build"] = jenkins_build
SPEC.loader.exec_module(jenkins_build)


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_json(self, url, tree=None):
        self.calls.append((url, tree))
        return {
            "name": "example",
            "url": "https://hed.sfp.ocs.oc-test.com/falcon/job/example",
            "lastBuild": {
                "number": 42,
                "url": "https://hed.sfp.ocs.oc-test.com/falcon/job/example/42/",
                "result": None,
                "building": True,
            },
        }

    def get_text(self, url, params=None):
        self.calls.append((url, params))
        return "abc", {"x-text-size": "3", "x-more-data": "true"}


class FakeStatusClient:
    def __init__(self, build_json, console_text=""):
        self.build_json = build_json
        self.console_text = console_text
        self.calls = []

    def get_json(self, url, tree=None):
        self.calls.append((url, tree))
        if url.endswith("/42"):
            return {**self.build_json, "url": url}
        return {
            "name": "vm",
            "url": "https://hed.sfp.ocs.oc-test.com/falcon/job/vm/job/feature%252Fdemo",
            "lastBuild": {
                "number": 42,
                "url": "https://hed.sfp.ocs.oc-test.com/falcon/job/vm/job/feature%252Fdemo/42/",
                "result": self.build_json.get("result"),
                "building": self.build_json.get("building"),
            },
        }

    def get_text(self, url, params=None):
        self.calls.append((url, params))
        return self.console_text, {
            "x-text-size": str(len(self.console_text.encode("utf-8"))),
            "x-more-data": "false",
        }


class FakeDownloadClient:
    def __init__(self, build_json, console_text, test_report=None, artifact_data=b"artifact"):
        self.build_json = build_json
        self.console_text = console_text
        self.test_report = test_report if test_report is not None else {"suites": []}
        self.artifact_data = artifact_data
        self.calls = []

    def get_json(self, url, tree=None):
        self.calls.append((url, tree))
        if url.endswith("/testReport"):
            return self.test_report
        if url.endswith("/42"):
            return {**self.build_json, "url": url}
        return {
            "name": "vm",
            "url": "https://hed.sfp.ocs.oc-test.com/falcon/job/vm/job/feature%252Fdemo",
            "lastBuild": {
                "number": 42,
                "url": "https://hed.sfp.ocs.oc-test.com/falcon/job/vm/job/feature%252Fdemo/42/",
                "result": self.build_json.get("result"),
                "building": self.build_json.get("building"),
            },
            "builds": [
                {
                    "number": 42,
                    "url": "https://hed.sfp.ocs.oc-test.com/falcon/job/vm/job/feature%252Fdemo/42/",
                    "result": self.build_json.get("result"),
                    "building": self.build_json.get("building"),
                }
            ],
        }

    def get_text(self, url, params=None):
        self.calls.append((url, params))
        return self.console_text, {
            "x-text-size": str(len(self.console_text.encode("utf-8"))),
            "x-more-data": "false",
        }

    def get_binary(self, url, max_bytes=None):
        self.calls.append((url, max_bytes))
        if max_bytes is not None and len(self.artifact_data) > max_bytes:
            raise jenkins_build.JenkinsError("artifact too large")
        return self.artifact_data


class FakeRecentBuildClient:
    def __init__(self, builds):
        self.builds = builds
        self.calls = []
        self.job_url = "https://hed.sfp.ocs.oc-test.com/falcon/job/vm/job/feature%252Fdemo"

    def get_json(self, url, tree=None):
        self.calls.append((url, tree))
        for number, build_json, _console in self.builds:
            if url.rstrip("/").endswith(f"/{number}"):
                return {**build_json, "number": number, "url": f"{self.job_url}/{number}"}
        latest_number, latest_json, _console = self.builds[0]
        return {
            "name": "vm",
            "url": self.job_url,
            "lastBuild": {
                "number": latest_number,
                "url": f"{self.job_url}/{latest_number}/",
                "result": latest_json.get("result"),
                "building": latest_json.get("building"),
            },
            "builds": [
                {
                    "number": number,
                    "url": f"{self.job_url}/{number}/",
                    "result": build_json.get("result"),
                    "building": build_json.get("building"),
                }
                for number, build_json, _console in self.builds
            ],
        }

    def get_text(self, url, params=None):
        self.calls.append((url, params))
        for number, _build_json, console in self.builds:
            if f"/{number}/" in url:
                return console, {
                    "x-text-size": str(len(console.encode("utf-8"))),
                    "x-more-data": "false",
                }
        return "", {"x-text-size": "0", "x-more-data": "false"}


class FakeHTTPResponse:
    def __init__(self, data=b"{}"):
        self.data = data
        self.offset = 0
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def read(self, size=-1):
        if size is None or size < 0:
            size = len(self.data) - self.offset
        chunk = self.data[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


class JenkinsBuildHelperTest(unittest.TestCase):
    def git(self, root, *args):
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return result.stdout.strip()

    def make_repo(self, branch="feature/demo", origin="git@github.example.com:orange/vm.git"):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.git(root, "config", "user.email", "codex@example.com")
        self.git(root, "config", "user.name", "Codex Test")
        (root / "README.md").write_text("test\n", encoding="utf-8")
        self.git(root, "add", "README.md")
        self.git(root, "commit", "-m", "initial")
        self.git(root, "checkout", "-b", branch)
        if origin:
            self.git(root, "remote", "add", "origin", origin)
        return tmp, root, self.git(root, "rev-parse", "HEAD")

    def test_normalize_build_url_with_double_encoded_branch(self):
        target = jenkins_build.parse_jenkins_url(
            "https://hed.sfp.ocs.oc-test.com/falcon/job/folder/job/pipeline/job/feature%252Fdemo/123/",
            jenkins_build.DEFAULT_BASE_URL,
        )

        self.assertEqual(target.base_url, "https://hed.sfp.ocs.oc-test.com/falcon")
        self.assertEqual(target.job_name, "folder/pipeline/feature/demo")
        self.assertEqual(target.job_segments, ["folder", "pipeline", "feature/demo"])
        self.assertEqual(target.build, 123)
        self.assertEqual(
            target.job_url,
            "https://hed.sfp.ocs.oc-test.com/falcon/job/folder/job/pipeline/job/feature%252Fdemo",
        )

    def test_normalize_job_name(self):
        job_name, segments, job_url = jenkins_build.job_name_to_url(
            "https://hed.sfp.ocs.oc-test.com/falcon",
            "folder/pipeline",
        )

        self.assertEqual(job_name, "folder/pipeline")
        self.assertEqual(segments, ["folder", "pipeline"])
        self.assertEqual(
            job_url,
            "https://hed.sfp.ocs.oc-test.com/falcon/job/folder/job/pipeline",
        )

    def test_repo_basename_from_origin(self):
        self.assertEqual(jenkins_build.repo_name_from_origin("vm.git"), "vm")
        self.assertEqual(jenkins_build.repo_name_from_origin("mpg.git"), "mpg")
        self.assertEqual(jenkins_build.repo_name_from_origin("git@github.example.com:orange/vm.git"), "vm")
        self.assertEqual(jenkins_build.repo_name_from_origin("https://github.example.com/orange/mpg.git"), "mpg")

    def test_current_branch_url_generation_double_encodes_branch_slash(self):
        job_name, segments, job_url = jenkins_build.current_job_to_url(
            "https://hed.sfp.ocs.oc-test.com/falcon",
            "vm",
            "release/12.4.0.3",
        )

        self.assertEqual(job_name, "vm/release/12.4.0.3")
        self.assertEqual(segments, ["vm", "release/12.4.0.3"])
        self.assertEqual(
            job_url,
            "https://hed.sfp.ocs.oc-test.com/falcon/job/vm/job/release%252F12.4.0.3",
        )

    def test_current_worktree_inference_from_repo_root_branch_and_head(self):
        tmp, root, head = self.make_repo(branch="release/12.4.0.3")
        with tmp:
            worktree = jenkins_build.infer_current_worktree(str(root))
            target = jenkins_build.target_from_current_worktree(
                worktree,
                "https://hed.sfp.ocs.oc-test.com/falcon",
            )

        self.assertEqual(worktree.repo_name, "vm")
        self.assertEqual(worktree.branch, "release/12.4.0.3")
        self.assertEqual(worktree.head_sha, head)
        self.assertEqual(
            target.job_url,
            "https://hed.sfp.ocs.oc-test.com/falcon/job/vm/job/release%252F12.4.0.3",
        )

    def test_normalize_current_target_fails_for_missing_origin(self):
        tmp, root, _ = self.make_repo(origin=None)
        with tmp:
            args = argparse.Namespace(
                base_url=jenkins_build.DEFAULT_BASE_URL,
                job_url=None,
                job_name=None,
                build=None,
                repo_root=str(root),
            )

            with self.assertRaisesRegex(jenkins_build.JenkinsError, "remote.origin.url is missing"):
                jenkins_build.normalize_target(args)

    def test_normalize_current_target_fails_for_detached_head(self):
        tmp, root, _ = self.make_repo()
        with tmp:
            self.git(root, "checkout", "--detach", "HEAD")
            args = argparse.Namespace(
                base_url=jenkins_build.DEFAULT_BASE_URL,
                job_url=None,
                job_name=None,
                build=None,
                repo_root=str(root),
            )

            with self.assertRaisesRegex(jenkins_build.JenkinsError, "detached"):
                jenkins_build.normalize_target(args)

    def test_latest_build_resolution(self):
        client = FakeClient()
        target = jenkins_build.NormalizedTarget(
            base_url="https://hed.sfp.ocs.oc-test.com/falcon",
            job_name="example",
            job_segments=["example"],
            job_url="https://hed.sfp.ocs.oc-test.com/falcon/job/example",
        )

        resolved, latest = jenkins_build.with_resolved_build(client, target)

        self.assertEqual(resolved.build, 42)
        self.assertEqual(resolved.build_url, "https://hed.sfp.ocs.oc-test.com/falcon/job/example/42")
        self.assertIsNotNone(latest)
        self.assertEqual(client.calls[0][0], target.job_url)

    def test_branch_and_sha_prefer_parameters(self):
        build_json = {
            "actions": [
                {
                    "parameters": [
                        {"name": "BRANCH_NAME", "value": "origin/feature/demo"},
                        {"name": "GIT_COMMIT", "value": "a" * 40},
                    ]
                }
            ],
            "changeSet": {"items": [{"commitId": "b" * 40}]},
        }
        console = f"Checking out Revision {'c' * 40} (origin/feature/other)"

        info = jenkins_build.extract_branch_sha(build_json, console_text=console)

        self.assertEqual(info["branch"], "feature/demo")
        self.assertEqual(info["sha"], "a" * 40)
        self.assertEqual(info["sha_candidates"][0]["source"], "parameter:GIT_COMMIT")

    def test_branch_sha_pair_for_target_branch_beats_library_sha_first(self):
        library_sha = "c" * 40
        repo_sha = "d" * 40
        console = "\n".join(
            [
                f"Checking out Revision {library_sha} (origin/master)",
                f"Checking out Revision {repo_sha} (origin/feature/demo)",
            ]
        )

        info = jenkins_build.extract_branch_sha(
            {},
            console_text=console,
            target_branch="feature/demo",
        )

        self.assertEqual(info["branch"], "feature/demo")
        self.assertEqual(info["sha"], repo_sha)
        self.assertEqual(info["sha_candidates"][0]["value"], library_sha)

    def test_progressive_console_offsets(self):
        client = FakeClient()
        chunk = jenkins_build.progressive_console(
            client,
            "https://hed.sfp.ocs.oc-test.com/falcon/job/example/42",
            start=0,
        )

        self.assertEqual(chunk.text, "abc")
        self.assertEqual(chunk.start, 0)
        self.assertEqual(chunk.next_start, 3)
        self.assertTrue(chunk.more_data)

    def test_classify_mockito_matcher_fixture(self):
        console = """
        org.mockito.exceptions.misusing.InvalidUseOfMatchersException:
        Invalid use of argument matchers!
        2 matchers expected, 1 recorded:
        """
        report = {
            "suites": [
                {
                    "name": "MockitoMatcherTest",
                    "cases": [
                        {
                            "className": "com.example.MockitoMatcherTest",
                            "name": "failsOnMixedMatchers",
                            "status": "FAILED",
                            "errorDetails": "InvalidUseOfMatchersException",
                        }
                    ],
                }
            ]
        }

        result = jenkins_build.classify_failure(console, report)

        self.assertEqual(result["failure_type"], "test_failure")
        self.assertFalse(result["likely_environmental"])
        self.assertTrue(
            any(signature["kind"] == "mockito_matcher_misuse" for signature in result["top_signatures"])
        )

    def test_classify_from_saved_evidence_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "console.txt").write_text("Could not resolve dependencies\n", encoding="utf-8")
            (root / "test_report.json").write_text(json.dumps({"suites": []}), encoding="utf-8")
            args = argparse.Namespace(evidence_dir=str(root))

            result = jenkins_build.cmd_classify(args)

        self.assertEqual(result["classification"]["failure_type"], "dependency_resolution")
        self.assertTrue(result["classification"]["likely_environmental"])

    def test_current_target_green_only_when_jenkins_sha_matches_head(self):
        tmp, root, head = self.make_repo()
        build_json = {
            "number": 42,
            "result": "SUCCESS",
            "building": False,
            "actions": [],
            "changeSet": {"items": []},
        }
        console = f"Checking out Revision {head} (origin/feature/demo)\nFinished: SUCCESS\n"
        client = FakeStatusClient(build_json, console)
        old_make_client = jenkins_build.make_client
        jenkins_build.make_client = lambda args: client
        try:
            with tmp:
                args = argparse.Namespace(
                    base_url=jenkins_build.DEFAULT_BASE_URL,
                    job_url=None,
                    job_name=None,
                    build=None,
                    repo_root=str(root),
                    username="user@example.com",
                    token_env=jenkins_build.DEFAULT_TOKEN_ENV,
                    timeout=30,
                    console_limit_bytes=500_000,
                )

                result = jenkins_build.cmd_current_target(args)
        finally:
            jenkins_build.make_client = old_make_client

        self.assertTrue(result["green_for_current_head"]["green"])
        self.assertEqual(result["repo_checkout_sha"], head)

    def test_current_target_successful_older_sha_is_not_green_for_current_head(self):
        tmp, root, head = self.make_repo()
        old_sha = "e" * 40
        self.assertNotEqual(old_sha, head)
        build_json = {
            "number": 42,
            "result": "SUCCESS",
            "building": False,
            "actions": [],
            "changeSet": {"items": []},
        }
        console = f"Checking out Revision {old_sha} (origin/feature/demo)\nFinished: SUCCESS\n"
        client = FakeStatusClient(build_json, console)
        old_make_client = jenkins_build.make_client
        jenkins_build.make_client = lambda args: client
        try:
            with tmp:
                args = argparse.Namespace(
                    base_url=jenkins_build.DEFAULT_BASE_URL,
                    job_url=None,
                    job_name=None,
                    build=None,
                    repo_root=str(root),
                    username="user@example.com",
                    token_env=jenkins_build.DEFAULT_TOKEN_ENV,
                    timeout=30,
                    console_limit_bytes=500_000,
                )

                result = jenkins_build.cmd_current_target(args)
        finally:
            jenkins_build.make_client = old_make_client

        self.assertFalse(result["green_for_current_head"]["green"])
        self.assertEqual(result["green_for_current_head"]["expected_sha"], head)
        self.assertEqual(result["green_for_current_head"]["jenkins_sha"], old_sha)
        self.assertIn("current HEAD", result["green_for_current_head"]["reason"])

    def test_console_search_redacts_sensitive_values(self):
        console = "\n".join(
            [
                "Authorization: Basic abc123",
                "Branch Specifier: */feature/demo",
                f"Checking out Revision {'f' * 40} (origin/feature/demo)",
                "[ERROR] token=supersecret password: dontprint",
                "Finished: FAILURE",
            ]
        )

        matches = jenkins_build.console_search_matches(console)
        text = "\n".join(match["text"] for match in matches)

        self.assertIn("Checking out Revision", text)
        self.assertIn("Branch Specifier", text)
        self.assertIn("Finished: FAILURE", text)
        self.assertNotIn("abc123", text)
        self.assertNotIn("supersecret", text)
        self.assertNotIn("dontprint", text)

    def test_redact_url_removes_query_and_userinfo(self):
        redacted = jenkins_build.redact_url(
            "https://codex:secret@example.com:8443/job/demo/42/api/json?token=secret"
        )

        self.assertEqual(redacted, "https://<redacted>@example.com:8443/job/demo/42/api/json")
        self.assertNotIn("secret", redacted)
        self.assertNotIn("token", redacted)

    def test_redact_json_preserves_author_and_redacts_secret_parameters(self):
        data = {
            "changeSet": {
                "items": [
                    {
                        "author": {"fullName": "Ada Lovelace"},
                        "msg": "Build fix",
                    }
                ]
            },
            "actions": [
                {
                    "parameters": [
                        {"name": "API_TOKEN", "value": "supersecretvalue"},
                        {"name": "BRANCH_NAME", "value": "feature/demo"},
                    ]
                }
            ],
        }

        redacted = jenkins_build.redact_json_value(data)

        self.assertEqual(redacted["changeSet"]["items"][0]["author"]["fullName"], "Ada Lovelace")
        self.assertEqual(redacted["actions"][0]["parameters"][0]["value"], "<redacted>")
        self.assertEqual(redacted["actions"][0]["parameters"][1]["value"], "feature/demo")

    def test_read_full_console_respects_limit_bytes(self):
        client = FakeStatusClient({}, "abcdef")

        console = jenkins_build.read_full_console(
            client,
            "https://hed.sfp.ocs.oc-test.com/falcon/job/example/42",
            limit_bytes=3,
        )

        self.assertEqual(console, "abc")

    def test_read_full_console_zero_limit_does_not_fetch(self):
        client = FakeStatusClient({}, "abcdef")

        console = jenkins_build.read_full_console(
            client,
            "https://hed.sfp.ocs.oc-test.com/falcon/job/example/42",
            limit_bytes=0,
        )

        self.assertEqual(console, "")
        self.assertEqual(client.calls, [])

    def test_download_failure_writes_redacted_evidence(self):
        secret = "supersecretvalue"
        os.environ["JENKINS_TEST_TOKEN"] = secret
        build_json = {
            "number": 42,
            "result": "FAILURE",
            "building": False,
            "actions": [
                {
                    "parameters": [
                        {"name": "API_TOKEN", "value": secret},
                        {"name": "BRANCH_NAME", "value": "feature/demo"},
                    ]
                }
            ],
            "changeSet": {"items": []},
            "artifacts": [{"fileName": "log.txt", "relativePath": "logs/log.txt"}],
        }
        console = f"[ERROR] token={secret} password: dontprint\nFinished: FAILURE\n"
        client = FakeDownloadClient(build_json, console)
        old_make_client = jenkins_build.make_client
        old_evidence_root = jenkins_build.EVIDENCE_ROOT
        jenkins_build.make_client = lambda args: client
        try:
            with tempfile.TemporaryDirectory() as tmp:
                jenkins_build.EVIDENCE_ROOT = Path(tmp)
                args = argparse.Namespace(
                    base_url=jenkins_build.DEFAULT_BASE_URL,
                    job_url="https://hed.sfp.ocs.oc-test.com/falcon/job/vm/job/feature%252Fdemo/42/",
                    job_name=None,
                    build=None,
                    repo_root=None,
                    username="user@example.com",
                    token_env="JENKINS_TEST_TOKEN",
                    timeout=30,
                    retries=0,
                    retry_backoff_seconds=0,
                    max_artifacts=20,
                    max_artifact_bytes=100,
                    max_total_artifact_bytes=100,
                    console_limit_bytes=jenkins_build.DEFAULT_CONSOLE_LIMIT,
                )

                result = jenkins_build.cmd_download_failure(args)

                evidence_dir = Path(result["evidence_dir"])
                console_text = (evidence_dir / "console.txt").read_text(encoding="utf-8")
                build_text = (evidence_dir / "build.json").read_text(encoding="utf-8")
                classification_text = (evidence_dir / "classification.json").read_text(encoding="utf-8")

                self.assertNotIn(secret, console_text)
                self.assertNotIn(secret, build_text)
                self.assertNotIn(secret, classification_text)
                self.assertIn("<redacted>", console_text)
                self.assertIn("<redacted>", build_text)
        finally:
            jenkins_build.make_client = old_make_client
            jenkins_build.EVIDENCE_ROOT = old_evidence_root
            os.environ.pop("JENKINS_TEST_TOKEN", None)

    def test_current_target_scans_recent_builds_for_current_head(self):
        tmp, root, head = self.make_repo()
        old_sha = "e" * 40
        client = FakeRecentBuildClient(
            [
                (
                    45,
                    {"result": "SUCCESS", "building": False, "actions": [], "changeSet": {"items": []}},
                    f"Checking out Revision {old_sha} (origin/feature/demo)\nFinished: SUCCESS\n",
                ),
                (
                    44,
                    {"result": "SUCCESS", "building": False, "actions": [], "changeSet": {"items": []}},
                    f"Checking out Revision {head} (origin/feature/demo)\nFinished: SUCCESS\n",
                ),
            ]
        )
        old_make_client = jenkins_build.make_client
        jenkins_build.make_client = lambda args: client
        try:
            with tmp:
                args = argparse.Namespace(
                    base_url=jenkins_build.DEFAULT_BASE_URL,
                    job_url=None,
                    job_name=None,
                    build=None,
                    repo_root=str(root),
                    username="user@example.com",
                    token_env=jenkins_build.DEFAULT_TOKEN_ENV,
                    timeout=30,
                    console_limit_bytes=jenkins_build.DEFAULT_CONSOLE_LIMIT,
                    scan_builds=10,
                )

                result = jenkins_build.cmd_current_target(args)
        finally:
            jenkins_build.make_client = old_make_client

        self.assertTrue(result["green_for_current_head"]["green"])
        self.assertEqual(result["matching_build"]["number"], 44)
        self.assertEqual(result["status"]["number"], 44)
        self.assertEqual([build["number"] for build in result["checked_builds"]], [45, 44])

    def test_wait_current_head_returns_completed_matching_build(self):
        tmp, root, head = self.make_repo()
        client = FakeRecentBuildClient(
            [
                (
                    46,
                    {"result": "SUCCESS", "building": False, "actions": [], "changeSet": {"items": []}},
                    f"Checking out Revision {head} (origin/feature/demo)\nFinished: SUCCESS\n",
                )
            ]
        )
        old_make_client = jenkins_build.make_client
        jenkins_build.make_client = lambda args: client
        try:
            with tmp:
                args = argparse.Namespace(
                    base_url=jenkins_build.DEFAULT_BASE_URL,
                    job_url=None,
                    job_name=None,
                    build=None,
                    repo_root=str(root),
                    username="user@example.com",
                    token_env=jenkins_build.DEFAULT_TOKEN_ENV,
                    timeout=30,
                    console_limit_bytes=jenkins_build.DEFAULT_CONSOLE_LIMIT,
                    scan_builds=10,
                    interval=0,
                    max_interval=0,
                    max_wait_seconds=1,
                )

                result = jenkins_build.cmd_wait_current_head(args)
        finally:
            jenkins_build.make_client = old_make_client

        self.assertEqual(result["matching_build"]["number"], 46)
        self.assertTrue(result["green_for_current_head"]["green"])
        self.assertEqual(result["polls"], 1)

    def test_client_retries_transient_http_errors(self):
        os.environ.pop("JENKINS_TEST_TOKEN_MISSING", None)
        old_urlopen = jenkins_build.urllib.request.urlopen
        calls = []

        def fake_urlopen(request, timeout):
            calls.append((request, timeout))
            if len(calls) == 1:
                raise jenkins_build.urllib.error.HTTPError(
                    request.full_url,
                    500,
                    "server error",
                    {},
                    io.BytesIO(b""),
                )
            return FakeHTTPResponse(b"ok")

        jenkins_build.urllib.request.urlopen = fake_urlopen
        try:
            client = jenkins_build.JenkinsClient(
                None,
                "JENKINS_TEST_TOKEN_MISSING",
                retries=1,
                retry_backoff_seconds=0,
            )
            data, _headers = client.request("https://example.com/job/demo")
        finally:
            jenkins_build.urllib.request.urlopen = old_urlopen

        self.assertEqual(data, b"ok")
        self.assertEqual(len(calls), 2)

    def test_client_does_not_retry_auth_errors(self):
        os.environ.pop("JENKINS_TEST_TOKEN_MISSING", None)
        old_urlopen = jenkins_build.urllib.request.urlopen
        calls = []

        def fake_urlopen(request, timeout):
            calls.append((request, timeout))
            raise jenkins_build.urllib.error.HTTPError(
                request.full_url,
                403,
                "forbidden",
                {},
                io.BytesIO(b""),
            )

        jenkins_build.urllib.request.urlopen = fake_urlopen
        try:
            client = jenkins_build.JenkinsClient(
                None,
                "JENKINS_TEST_TOKEN_MISSING",
                retries=3,
                retry_backoff_seconds=0,
            )
            with self.assertRaisesRegex(jenkins_build.JenkinsError, "HTTP 403"):
                client.request("https://example.com/job/demo")
        finally:
            jenkins_build.urllib.request.urlopen = old_urlopen

        self.assertEqual(len(calls), 1)

    def test_wait_current_head_parser_options(self):
        parser = jenkins_build.build_parser()
        args = parser.parse_args(
            [
                "wait-current-head",
                "--username",
                "user@example.com",
                "--scan-builds",
                "7",
                "--max-wait-seconds",
                "1",
            ]
        )

        self.assertEqual(args.command, "wait-current-head")
        self.assertEqual(args.scan_builds, 7)
        self.assertEqual(args.max_wait_seconds, 1)


if __name__ == "__main__":
    unittest.main()
