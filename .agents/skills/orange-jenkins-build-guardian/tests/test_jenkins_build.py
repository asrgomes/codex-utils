import argparse
import importlib.util
import json
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


if __name__ == "__main__":
    unittest.main()
