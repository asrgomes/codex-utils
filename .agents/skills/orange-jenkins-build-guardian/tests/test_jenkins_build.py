import argparse
import importlib.util
import json
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


class JenkinsBuildHelperTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
