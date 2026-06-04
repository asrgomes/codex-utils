import contextlib
import io
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sfp_release_drift.py"
SPEC = importlib.util.spec_from_file_location("sfp_release_drift", SCRIPT)
assert SPEC is not None
sfp_release_drift = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = sfp_release_drift
SPEC.loader.exec_module(sfp_release_drift)

MR_SUBJECT = "Merge-Request: 123 from 'source' into 'target'"


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def runtime_config(
    root: Path,
    repositories: list[Path],
    verbose: bool = False,
    ignore_non_material_commits: bool = False,
    suppressed_branches: list[str] | None = None,
) -> dict[str, object]:
    return {
        "config_file": root / "config.toml",
        "verbose": verbose,
        "tmp_dir": root / "audit-work",
        "max_versions": 5,
        "ignore_non_material_commits": ignore_non_material_commits,
        "suppressed_branches": suppressed_branches or [],
        "repositories": [str(repository) for repository in repositories],
        "output_report_file": root / "report.md",
        "slack_text_file": root / "slack.txt",
    }


def write_toml_config(root: str | Path, body: str, filename: str = "config.toml") -> Path:
    path = Path(root) / filename
    path.write_text(body, encoding="utf-8")
    return path


class TtyStringIO(io.StringIO):
    def isatty(self) -> bool:
        return True


class ReleaseDriftTest(unittest.TestCase):
    def test_numeric_version_sorting(self):
        branches = [
            sfp_release_drift.parse_release_branch("release/12.4.0.3"),
            sfp_release_drift.parse_release_branch("release/12.10.0.0"),
            sfp_release_drift.parse_release_branch("release/12.4.1.0"),
        ]
        sorted_names = [
            branch.name
            for branch in sfp_release_drift.sort_newest_first(branches)
        ]
        self.assertEqual(
            sorted_names,
            ["release/12.10.0.0", "release/12.4.1.0", "release/12.4.0.3"],
        )

    def test_selects_newest_five(self):
        branches = [
            sfp_release_drift.parse_release_branch(f"release/26.{i}.0.0")
            for i in range(1, 8)
        ]
        selected = sfp_release_drift.select_newest(branches, 5)
        self.assertEqual(
            [branch.name for branch in selected],
            [
                "release/26.7.0.0",
                "release/26.6.0.0",
                "release/26.5.0.0",
                "release/26.4.0.0",
                "release/26.3.0.0",
            ],
        )

    def test_counterpart_oci_branch_rejects_non_aws_branch(self):
        branch = sfp_release_drift.parse_release_branch("release/26.4.0.3")
        self.assertIsNotNone(branch)

        with self.assertRaisesRegex(ValueError, "Expected AWS release branch major 12"):
            sfp_release_drift.counterpart_oci_branch(branch)

    def test_parse_args_requires_config_file(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                sfp_release_drift.parse_args([])

        self.assertEqual(raised.exception.code, 2)

    def test_parse_args_accepts_explicit_config_file(self):
        args = sfp_release_drift.parse_args(["-f", "custom.toml"])
        self.assertEqual(args.config, Path("custom.toml"))

    def test_old_cli_flags_are_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                sfp_release_drift.parse_args(["--repo-list", "repositories.txt"])

    def test_long_config_alias_is_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                sfp_release_drift.parse_args(["--config", "config.toml"])

    def test_load_config_accepts_valid_toml_and_resolves_relative_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = write_toml_config(
                root,
                """
verbose = true
tmp_dir = "tmp"
max_versions = 5
repositories = ["ssh://example/repo-a.git", "ssh://example/repo-b.git"]
output_report_file = "report.md"
slack_text_file = "slack.txt"
""",
            )

            config = sfp_release_drift.load_config(config_path)

            self.assertTrue(config["verbose"])
            self.assertEqual(config["tmp_dir"], root / "tmp")
            self.assertEqual(config["max_versions"], 5)
            self.assertFalse(config["ignore_non_material_commits"])
            self.assertEqual(config["suppressed_branches"], [])
            self.assertEqual(config["repositories"], ["ssh://example/repo-a.git", "ssh://example/repo-b.git"])
            self.assertEqual(config["output_report_file"], root / "report.md")
            self.assertEqual(config["slack_text_file"], root / "slack.txt")

    def test_checked_in_config_writes_jenkins_artifacts_to_archive_paths(self):
        root = SCRIPT.parents[1]
        config = sfp_release_drift.load_config(root / "config.toml")

        self.assertEqual(config["output_report_file"], root / "drift-report.md")
        self.assertEqual(config["slack_text_file"], root / "drift-report-slack.txt")
        self.assertTrue(config["ignore_non_material_commits"])
        self.assertEqual(
            config["suppressed_branches"],
            [
                "release/12.4.2.0",
                "release/26.4.2.0",
                "release/12.4.1.0",
                "release/26.4.1.0",
            ],
        )

    def test_load_config_rejects_non_bool_ignore_non_material_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = write_toml_config(
                tmp,
                """
verbose = false
tmp_dir = "/tmp/drift"
max_versions = 5
ignore_non_material_commits = "yes"
repositories = ["ssh://example/repo.git"]
output_report_file = "report.md"
""",
            )

            with self.assertRaisesRegex(
                sfp_release_drift.ConfigError,
                "ignore_non_material_commits.*true or false",
            ):
                sfp_release_drift.load_config(config_path)

    def test_load_config_accepts_suppressed_branches(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = write_toml_config(
                tmp,
                """
verbose = false
tmp_dir = "/tmp/drift"
max_versions = 5
suppressed_branches = ["release/26.4.1.0", " release/26.4.0.3 "]
repositories = ["ssh://example/repo.git"]
output_report_file = "report.md"
""",
            )

            config = sfp_release_drift.load_config(config_path)

            self.assertEqual(
                config["suppressed_branches"],
                ["release/26.4.1.0", "release/26.4.0.3"],
            )

    def test_load_config_rejects_invalid_suppressed_branches(self):
        invalid_configs = [
            'suppressed_branches = "release/26.4.1.0"',
            'suppressed_branches = ["release/26.4.1.0", ""]',
            'suppressed_branches = ["release/26.4.1.0", false]',
        ]
        for suppressed_config in invalid_configs:
            with self.subTest(suppressed_config=suppressed_config):
                with tempfile.TemporaryDirectory() as tmp:
                    config_path = write_toml_config(
                        tmp,
                        f"""
verbose = false
tmp_dir = "/tmp/drift"
max_versions = 5
{suppressed_config}
repositories = ["ssh://example/repo.git"]
output_report_file = "report.md"
""",
                    )

                    with self.assertRaisesRegex(
                        sfp_release_drift.ConfigError,
                        "suppressed_branches.*non-empty string",
                    ):
                        sfp_release_drift.load_config(config_path)

    def test_load_config_rejects_misspelled_repositories_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = write_toml_config(
                tmp,
                """
verbose = false
tmp_dir = "/tmp/drift"
max_versions = 5
repsitories = ["ssh://example/repo.git"]
output_report_file = "report.md"
""",
            )

            with self.assertRaisesRegex(sfp_release_drift.ConfigError, "repsitories.*repositories"):
                sfp_release_drift.load_config(config_path)

    def test_load_config_rejects_non_ssh_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = write_toml_config(
                tmp,
                """
verbose = false
tmp_dir = "/tmp/drift"
max_versions = 5
repositories = ["https://example/repo.git"]
output_report_file = "report.md"
""",
            )

            with self.assertRaisesRegex(sfp_release_drift.ConfigError, "ssh://"):
                sfp_release_drift.load_config(config_path)

    def test_load_config_requires_markdown_report_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = write_toml_config(
                tmp,
                """
verbose = false
tmp_dir = "/tmp/drift"
max_versions = 5
repositories = ["ssh://example/repo.git"]
output_report_file = "report.txt"
""",
            )

            with self.assertRaisesRegex(sfp_release_drift.ConfigError, "must end with '.md'"):
                sfp_release_drift.load_config(config_path)

    def test_main_reports_config_errors_to_stderr_and_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = write_toml_config(
                tmp,
                """
verbose = false
tmp_dir = "/tmp/drift"
max_versions = 5
repositories = []
output_report_file = "report.md"
""",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = sfp_release_drift.main(["-f", str(config_path)])

            self.assertEqual(exit_code, 1)
            self.assertIn("# SFP Release Drift Report", stdout.getvalue())
            self.assertIn("repositories", stdout.getvalue())
            self.assertIn("ERROR Config key 'repositories' must be a non-empty list", stderr.getvalue())

    def test_main_uses_toml_config_for_output_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = write_toml_config(
                root,
                """
verbose = false
tmp_dir = "tmp"
max_versions = 5
repositories = ["ssh://example/repo.git"]
output_report_file = "report.md"
slack_text_file = "slack.txt"
""",
            )
            report = {
                "generated_at": "2026-06-03T17:35:57Z",
                "status": "pass",
                "config": {
                    "config_file": str(config_path),
                    "tmp_dir": str(root / "tmp"),
                    "max_versions": 5,
                    "ignore_non_material_commits": False,
                },
                "repositories": [],
                "findings": [],
                "ignored_non_material_commits": [],
            }

            with contextlib.redirect_stderr(io.StringIO()):
                with mock.patch.object(sfp_release_drift, "run_audit", return_value=report):
                    exit_code = sfp_release_drift.main(["-f", str(config_path)])

            self.assertEqual(exit_code, 0)
            self.assertTrue((root / "report.md").exists())
            self.assertTrue((root / "slack.txt").exists())

    def test_main_requires_config_file(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                sfp_release_drift.main([])

        self.assertEqual(raised.exception.code, 2)

    def test_verbose_writes_detailed_progress_to_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_remote(root, drift=False)
            config = runtime_config(root, [remote], verbose=True)
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                report = sfp_release_drift.run_audit(
                    config=config,
                    logger=sfp_release_drift.ProgressLogger(verbose=True),
                )

            self.assertEqual(report["status"], "pass")
            self.assertIn("INFO  Auditing 1 configured repository", stderr.getvalue())
            self.assertIn("DEBUG Repository URL:", stderr.getvalue())
            self.assertIn("DEBUG remote: selected AWS branches:", stderr.getvalue())

    def test_completion_summary_reports_no_missing_commits_on_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_remote(root, drift=False)
            config = runtime_config(root, [remote])
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                report = sfp_release_drift.run_audit(config=config, logger=sfp_release_drift.ProgressLogger())
                sfp_release_drift.log_completion_summary(report, sfp_release_drift.ProgressLogger())

            self.assertEqual(report["status"], "pass")
            self.assertIn(
                "INFO  Drift analysis complete: no missing commits found in 1 repositories scanned",
                stderr.getvalue(),
            )

    def test_completion_summary_reports_repository_count_on_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_remote(root, drift=True)
            config = runtime_config(root, [remote])
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                report = sfp_release_drift.run_audit(config=config, logger=sfp_release_drift.ProgressLogger())
                sfp_release_drift.log_completion_summary(report, sfp_release_drift.ProgressLogger())

            self.assertEqual(report["status"], "fail")
            self.assertIn(
                "ERROR Drift analysis complete: found 1 repositories with at least one branch missing commits",
                stderr.getvalue(),
            )

    def test_completion_summary_reports_non_drift_failures(self):
        report = sfp_release_drift.config_error_report(Path("config.toml"), "bad config")
        stream = io.StringIO()

        sfp_release_drift.log_completion_summary(report, sfp_release_drift.ProgressLogger(stream=stream))

        self.assertIn(
            "ERROR Drift analysis failed before finding branch drift: 1 finding(s)",
            stream.getvalue(),
        )

    def test_progress_logger_uses_plain_severity_labels_for_redirected_output(self):
        stream = io.StringIO()
        logger = sfp_release_drift.ProgressLogger(verbose=True, stream=stream)

        logger.info("start")
        logger.debug("details")
        logger.warn("drift")
        logger.error("failure")

        output = stream.getvalue().splitlines()
        self.assertEqual(output[0], "INFO  start")
        self.assertEqual(output[1], "DEBUG details")
        self.assertEqual(output[2], "WARN  drift")
        self.assertEqual(output[3], "ERROR failure")
        self.assertNotIn("\033[", stream.getvalue())

    def test_progress_logger_colorizes_whole_log_line_for_color_capable_terminal(self):
        stream = TtyStringIO()
        with mock.patch.dict(sfp_release_drift.os.environ, {"TERM": "xterm-256color"}, clear=True):
            logger = sfp_release_drift.ProgressLogger(stream=stream)
            logger.warn("drift")

        self.assertEqual(stream.getvalue(), "\033[33mWARN  drift\033[0m\n")

    def test_progress_logger_colorizes_debug_as_gray(self):
        stream = TtyStringIO()
        with mock.patch.dict(sfp_release_drift.os.environ, {"TERM": "xterm-256color"}, clear=True):
            logger = sfp_release_drift.ProgressLogger(verbose=True, stream=stream)
            logger.debug("details")

        self.assertEqual(stream.getvalue(), "\033[2;90mDEBUG details\033[0m\n")

    def test_progress_logger_keeps_info_in_default_terminal_color(self):
        stream = TtyStringIO()
        with mock.patch.dict(sfp_release_drift.os.environ, {"TERM": "xterm-256color"}, clear=True):
            logger = sfp_release_drift.ProgressLogger(stream=stream)
            logger.info("start")

        self.assertEqual(stream.getvalue(), "INFO  start\n")
        self.assertNotIn("\033[", stream.getvalue())

    def test_progress_logger_colorizes_error_as_bold_red(self):
        stream = TtyStringIO()
        with mock.patch.dict(sfp_release_drift.os.environ, {"TERM": "xterm-256color"}, clear=True):
            logger = sfp_release_drift.ProgressLogger(stream=stream)
            logger.error("failure")

        self.assertEqual(stream.getvalue(), "\033[1;31mERROR failure\033[0m\n")

    def test_progress_logger_does_not_colorize_when_no_color_is_set(self):
        stream = TtyStringIO()
        with mock.patch.dict(
            sfp_release_drift.os.environ,
            {"TERM": "xterm-256color", "NO_COLOR": "1"},
            clear=True,
        ):
            logger = sfp_release_drift.ProgressLogger(stream=stream)
            logger.error("failure")

        self.assertEqual(stream.getvalue(), "ERROR failure\n")

    def test_markdown_report_groups_drift_by_repository_and_target_branch(self):
        report = {
            "generated_at": "2026-06-03T17:35:57Z",
            "status": "fail",
            "repositories": [
                {
                    "repository": "mpg.git",
                    "selected_branches": {
                        "aws": [
                            "release/12.4.2.0",
                            "release/12.4.1.0",
                            "release/12.4.0.3",
                        ],
                        "oci": [
                            "release/26.4.2.0",
                            "release/26.4.1.0",
                            "release/26.4.0.3",
                        ],
                    },
                }
            ],
            "findings": [
                {
                    "type": "commit_drift",
                    "check": "aws_to_oci",
                    "repository": "mpg.git",
                    "from_branch": "release/12.4.2.0",
                    "to_branch": "release/26.4.2.0",
                    "commit_count": 2,
                    "commits": [
                        {
                            "hash": "b7d6f790aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                            "subject": "Merge-Request: 27059",
                        },
                        {
                            "hash": "d68e6270bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                            "subject": "Merge branch",
                        },
                    ],
                },
                {
                    "type": "commit_drift",
                    "check": "oci_adjacent",
                    "repository": "mpg.git",
                    "from_branch": "release/26.4.1.0",
                    "to_branch": "release/26.4.2.0",
                    "commit_count": 1,
                    "commits": [
                        {
                            "hash": "8c66ee76cccccccccccccccccccccccccccccccc",
                            "subject": "Merge-Request: 26311",
                        }
                    ],
                },
                {
                    "type": "commit_drift",
                    "check": "aws_adjacent",
                    "repository": "mpg.git",
                    "from_branch": "release/12.4.1.0",
                    "to_branch": "release/12.4.2.0",
                    "commit_count": 1,
                    "commits": [
                        {
                            "hash": "7932f851dddddddddddddddddddddddddddddddd",
                            "subject": "Merge-Request: 26298",
                        }
                    ],
                },
            ],
        }

        markdown = sfp_release_drift.render_markdown(report)

        self.assertIn("- Scanned branches\n  - AWS:", markdown)
        self.assertIn("    - `release/12.4.2.0`", markdown)
        self.assertIn("    - `release/26.4.2.0`", markdown)
        self.assertIn("## REPOSITORY: `mpg.git`", markdown)
        self.assertIn("## DRIFT DETECTED IN BRANCH `release/26.4.2.0`", markdown)
        self.assertIn("### Missing 2 commits from `release/12.4.2.0`", markdown)
        self.assertIn("### Missing 1 commit from `release/26.4.1.0`", markdown)
        self.assertIn("- `b7d6f790 Merge-Request: 27059`", markdown)
        self.assertIn("## DRIFT DETECTED IN BRANCH `release/12.4.2.0`", markdown)

    def test_commit_counts_are_rendered_with_singular_or_plural_labels(self):
        findings = []
        sfp_release_drift.add_commit_drift_finding(
            findings=findings,
            check="aws_to_oci",
            repo_url="ssh://example/mpg.git",
            repo_name="mpg.git",
            from_branch="release/12.4.2.0",
            to_branch="release/26.4.2.0",
            commits=[
                {
                    "hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "subject": "single",
                }
            ],
        )
        sfp_release_drift.add_commit_drift_finding(
            findings=findings,
            check="aws_to_oci",
            repo_url="ssh://example/mpg.git",
            repo_name="mpg.git",
            from_branch="release/12.4.1.0",
            to_branch="release/26.4.1.0",
            commits=[
                {
                    "hash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    "subject": "first",
                },
                {
                    "hash": "cccccccccccccccccccccccccccccccccccccccc",
                    "subject": "second",
                },
            ],
        )

        self.assertIn("1 commit from", findings[0]["message"])
        self.assertIn("2 commits from", findings[1]["message"])
        self.assertNotIn("commit(s)", findings[0]["message"])
        self.assertNotIn("commit(s)", findings[1]["message"])

        report = {
            "generated_at": "2026-06-03T17:35:57Z",
            "status": "fail",
            "config": {
                "config_file": "config.toml",
                "tmp_dir": "work",
                "max_versions": 5,
                "ignore_non_material_commits": False,
            },
            "repositories": [],
            "findings": findings,
            "ignored_non_material_commits": [],
        }

        slack = sfp_release_drift.render_slack_text(report, max_commits_per_finding=1)
        self.assertIn("1 more commit in archived report", slack)
        self.assertNotIn("commit(s)", slack)

    def test_clean_git_fixture_has_no_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_remote(root, drift=False)

            report = sfp_release_drift.run_audit(runtime_config(root, [remote]))

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["findings"], [])

    def test_initialized_work_dir_without_origin_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_remote(root, drift=False)
            repo_dir = root / "audit-work" / "initialized"
            subprocess.run(["git", "init", str(repo_dir)], check=True, stdout=subprocess.PIPE)

            sfp_release_drift.ensure_repo_fetched(repo_dir, str(remote))

            branches = sfp_release_drift.remote_release_branch_names(repo_dir)
            self.assertIn("release/12.4.0.3", branches)
            self.assertIn("release/26.4.0.3", branches)

    def test_git_errors_during_drift_checks_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_remote(root, drift=False)

            with mock.patch.object(
                sfp_release_drift,
                "pending_commits",
                side_effect=RuntimeError("git log failed"),
            ):
                report = sfp_release_drift.audit_repository(str(remote), root / "audit-work" / "repo", 5)

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["findings"][-1]["type"], "repo_error")
            self.assertEqual(report["findings"][-1]["check"], "drift")
            self.assertIn("git log failed", report["findings"][-1]["message"])

    def test_aws_to_oci_drift_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_remote(root, drift=True)

            report = sfp_release_drift.run_audit(runtime_config(root, [remote]))

            self.assertEqual(report["status"], "fail")
            checks = {finding["check"] for finding in report["findings"]}
            self.assertIn("aws_to_oci", checks)
            self.assertTrue(
                any(finding.get("commit_count", 0) > 0 for finding in report["findings"])
            )

    def test_suppressed_target_branch_drift_does_not_fail_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_single_pair_remote(root, [("real branch fix", True)])
            config = runtime_config(
                root,
                [remote],
                suppressed_branches=["release/26.4.0.3"],
            )
            stream = io.StringIO()

            report = sfp_release_drift.run_audit(config)
            sfp_release_drift.log_completion_summary(
                report,
                sfp_release_drift.ProgressLogger(stream=stream),
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["findings"], [])
            self.assertEqual(report["config"]["suppressed_branches"], ["release/26.4.0.3"])

            markdown = sfp_release_drift.render_markdown(report)
            self.assertIn("No release-branch drift detected.", markdown)
            self.assertNotIn("Suppressed branches", markdown)
            self.assertNotIn("release/26.4.0.3", markdown)

            slack = sfp_release_drift.render_slack_text(report, max_commits_per_finding=10)
            self.assertEqual(slack, "SFP release-branch drift audit passed.")
            self.assertIn("no missing commits found", stream.getvalue())
            self.assertNotIn("unsuppressed", stream.getvalue())

    def test_suppressed_source_branch_does_not_suppress_target_violation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_single_pair_remote(root, [("real branch fix", True)])

            report = sfp_release_drift.run_audit(
                runtime_config(root, [remote], suppressed_branches=["release/12.4.0.3"])
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(len(report["findings"]), 1)
            self.assertEqual(report["findings"][0]["to_branch"], "release/26.4.0.3")

    def test_suppressed_missing_target_branch_does_not_fail_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_missing_oci_remote(root)

            report = sfp_release_drift.run_audit(
                runtime_config(root, [remote], suppressed_branches=["release/26.4.0.3"])
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["findings"], [])

    def test_pending_commits_include_tree_and_parent_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_single_pair_remote(root, [(MR_SUBJECT, False)])
            repo_dir = root / "audit-work" / "repo"
            sfp_release_drift.ensure_repo_fetched(repo_dir, str(remote))

            commits = sfp_release_drift.pending_commits(
                repo_dir,
                "release/12.4.0.3",
                "release/26.4.0.3",
            )

            self.assertEqual(len(commits), 1)
            self.assertIn("tree", commits[0])
            self.assertIn("parents", commits[0])
            self.assertEqual(len(commits[0]["parents"]), 1)

    def test_ignore_disabled_preserves_empty_mr_drift_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_single_pair_remote(root, [(MR_SUBJECT, False)])

            report = sfp_release_drift.run_audit(runtime_config(root, [remote]))

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["findings"][0]["commit_count"], 1)
            self.assertEqual(report["ignored_non_material_commits"], [])

    def test_noop_branch_pair_is_ignored_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subject = "metadata refresh"
            remote = self.create_single_pair_remote(root, [(subject, False)])
            config = runtime_config(root, [remote], ignore_non_material_commits=True)
            stream = io.StringIO()

            report = sfp_release_drift.run_audit(config)
            sfp_release_drift.log_completion_summary(
                report,
                sfp_release_drift.ProgressLogger(stream=stream),
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["findings"], [])
            self.assertEqual(sfp_release_drift.ignored_non_material_commit_count(report), 1)

            markdown = sfp_release_drift.render_markdown(report)
            self.assertIn("No release-branch drift detected.", markdown)
            self.assertNotIn("Ignore verified non-material commits", markdown)
            self.assertNotIn("Ignored verified non-material commits", markdown)
            self.assertNotIn("## Ignored non-material commits", markdown)
            self.assertNotIn(subject, markdown)

            slack = sfp_release_drift.render_slack_text(report, max_commits_per_finding=10)
            self.assertEqual(slack, "SFP release-branch drift audit passed.")
            self.assertIn(
                "INFO  Drift analysis complete: no missing commits found",
                stream.getvalue(),
            )
            self.assertNotIn("ignored", stream.getvalue())

    def test_branch_pair_with_file_changes_is_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_single_pair_remote(root, [(MR_SUBJECT, True)])

            report = sfp_release_drift.run_audit(
                runtime_config(root, [remote], ignore_non_material_commits=True)
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["findings"][0]["commit_count"], 1)
            self.assertEqual(report["ignored_non_material_commits"], [])

    def test_mr_subject_is_not_required_for_noop_branch_pair_ignore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_single_pair_remote(root, [("Merge-Request: 123", False)])

            report = sfp_release_drift.run_audit(
                runtime_config(root, [remote], ignore_non_material_commits=True)
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["findings"], [])
            self.assertEqual(sfp_release_drift.ignored_non_material_commit_count(report), 1)

    def test_failed_noop_merge_verification_is_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commits = [
                {"raw": "unparseable"},
                {
                    "hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "short_hash": "aaaaaaaa",
                    "author": "Test User",
                    "date": "2026-06-03T17:35:57+00:00",
                    "tree": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                    "parents": ["cccccccccccccccccccccccccccccccccccccccc"],
                    "subject": MR_SUBJECT,
                },
            ]

            material, ignored = sfp_release_drift.split_material_and_ignored_commits(
                root,
                commits,
                ignore_non_material_commits=True,
                from_branch="release/12.4.0.3",
                to_branch="release/26.4.0.3",
            )

            self.assertEqual(material, commits)
            self.assertEqual(ignored, [])

    def test_branch_pair_with_file_changes_reports_all_pending_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_single_pair_remote(
                root,
                [
                    (MR_SUBJECT, False),
                    ("real branch fix", True),
                ],
            )
            stream = io.StringIO()

            report = sfp_release_drift.run_audit(
                runtime_config(root, [remote], ignore_non_material_commits=True)
            )
            sfp_release_drift.log_completion_summary(
                report,
                sfp_release_drift.ProgressLogger(stream=stream),
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(len(report["findings"]), 1)
            self.assertEqual(report["findings"][0]["commit_count"], 2)
            self.assertEqual(sfp_release_drift.ignored_non_material_commit_count(report), 0)

            markdown = sfp_release_drift.render_markdown(report)
            self.assertIn("### Missing 2 commits from `release/12.4.0.3`", markdown)
            self.assertNotIn("## Ignored non-material commits", markdown)
            self.assertIn(MR_SUBJECT, markdown)

            slack = sfp_release_drift.render_slack_text(report, max_commits_per_finding=10)
            self.assertIn("failed with 1 finding(s).", slack)
            self.assertIn("real branch fix", slack)
            self.assertIn(MR_SUBJECT, slack)
            self.assertNotIn("ignored", stream.getvalue())

    def test_conflicting_merge_tree_is_material(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_conflicting_single_pair_remote(root)

            report = sfp_release_drift.run_audit(
                runtime_config(root, [remote], ignore_non_material_commits=True)
            )

            self.assertEqual(report["status"], "fail")
            self.assertEqual(len(report["findings"]), 1)
            self.assertEqual(report["findings"][0]["commit_count"], 1)
            self.assertEqual(sfp_release_drift.ignored_non_material_commit_count(report), 0)

    def test_noop_merge_commit_regression_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remote = self.create_noop_merge_commit_remote(root)

            report = sfp_release_drift.run_audit(
                runtime_config(root, [remote], ignore_non_material_commits=True)
            )

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["findings"], [])
            self.assertEqual(sfp_release_drift.ignored_non_material_commit_count(report), 2)

    def create_single_pair_remote(self, root: Path, drift_commits: list[tuple[str, bool]]) -> Path:
        remote = root / "single-remote.git"
        work = root / "single-work"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "init", str(work)], check=True, stdout=subprocess.PIPE)
        git(work, "config", "user.email", "test@example.com")
        git(work, "config", "user.name", "Test User")

        (work / "root.txt").write_text("root\n", encoding="utf-8")
        git(work, "add", "root.txt")
        git(work, "commit", "-m", "root")
        initial_branch = git(work, "branch", "--show-current").stdout.strip()

        git(work, "checkout", "-b", "release/12.4.0.3")
        git(work, "checkout", initial_branch)
        git(work, "checkout", "-b", "release/26.4.0.3")
        git(work, "checkout", "release/12.4.0.3")

        for index, (subject, has_file_change) in enumerate(drift_commits, start=1):
            if has_file_change:
                path = work / f"material-{index}.txt"
                path.write_text(f"material {index}\n", encoding="utf-8")
                git(work, "add", path.name)
                git(work, "commit", "-m", subject)
            else:
                git(work, "commit", "--allow-empty", "-m", subject)

        git(work, "remote", "add", "origin", str(remote))
        git(work, "push", "origin", "release/12.4.0.3")
        git(work, "push", "origin", "release/26.4.0.3")
        return remote

    def create_conflicting_single_pair_remote(self, root: Path) -> Path:
        remote = root / "conflict-remote.git"
        work = root / "conflict-work"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "init", str(work)], check=True, stdout=subprocess.PIPE)
        git(work, "config", "user.email", "test@example.com")
        git(work, "config", "user.name", "Test User")

        (work / "root.txt").write_text("root\n", encoding="utf-8")
        git(work, "add", "root.txt")
        git(work, "commit", "-m", "root")
        initial_branch = git(work, "branch", "--show-current").stdout.strip()

        git(work, "checkout", "-b", "release/12.4.0.3")
        (work / "root.txt").write_text("source\n", encoding="utf-8")
        git(work, "add", "root.txt")
        git(work, "commit", "-m", "source conflict change")

        git(work, "checkout", initial_branch)
        git(work, "checkout", "-b", "release/26.4.0.3")
        (work / "root.txt").write_text("target\n", encoding="utf-8")
        git(work, "add", "root.txt")
        git(work, "commit", "-m", "target conflict change")

        git(work, "remote", "add", "origin", str(remote))
        git(work, "push", "origin", "release/12.4.0.3")
        git(work, "push", "origin", "release/26.4.0.3")
        return remote

    def create_noop_merge_commit_remote(self, root: Path) -> Path:
        remote = root / "noop-merge-remote.git"
        work = root / "noop-merge-work"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "init", str(work)], check=True, stdout=subprocess.PIPE)
        git(work, "config", "user.email", "test@example.com")
        git(work, "config", "user.name", "Test User")

        (work / "root.txt").write_text("root\n", encoding="utf-8")
        git(work, "add", "root.txt")
        git(work, "commit", "-m", "root")
        initial_branch = git(work, "branch", "--show-current").stdout.strip()

        git(work, "checkout", "-b", "release/12.4.0.3")
        (work / "temporary.txt").write_text("temporary source change\n", encoding="utf-8")
        git(work, "add", "temporary.txt")
        git(work, "commit", "-m", "temporary source drift")

        git(work, "checkout", initial_branch)
        git(work, "checkout", "-b", "release/26.4.0.3")
        (work / "target.txt").write_text("target release content\n", encoding="utf-8")
        git(work, "add", "target.txt")
        git(work, "commit", "-m", "target release content")

        git(work, "checkout", "release/12.4.0.3")
        git(work, "merge", "--no-ff", "--no-commit", "release/26.4.0.3")
        git(work, "rm", "temporary.txt")
        git(work, "commit", "-m", MR_SUBJECT)

        git(work, "remote", "add", "origin", str(remote))
        git(work, "push", "origin", "release/12.4.0.3")
        git(work, "push", "origin", "release/26.4.0.3")
        return remote

    def create_missing_oci_remote(self, root: Path) -> Path:
        remote = root / "missing-oci-remote.git"
        work = root / "missing-oci-work"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "init", str(work)], check=True, stdout=subprocess.PIPE)
        git(work, "config", "user.email", "test@example.com")
        git(work, "config", "user.name", "Test User")

        (work / "root.txt").write_text("root\n", encoding="utf-8")
        git(work, "add", "root.txt")
        git(work, "commit", "-m", "root")

        git(work, "checkout", "-b", "release/12.4.0.3")
        git(work, "remote", "add", "origin", str(remote))
        git(work, "push", "origin", "release/12.4.0.3")
        return remote

    def create_remote(self, root: Path, drift: bool) -> Path:
        remote = root / "remote.git"
        work = root / "work"
        subprocess.run(["git", "init", "--bare", str(remote)], check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "init", str(work)], check=True, stdout=subprocess.PIPE)
        git(work, "config", "user.email", "test@example.com")
        git(work, "config", "user.name", "Test User")

        (work / "root.txt").write_text("root\n", encoding="utf-8")
        git(work, "add", "root.txt")
        git(work, "commit", "-m", "root")

        git(work, "checkout", "-b", "release/12.4.0.2")
        (work / "aws-old.txt").write_text("aws old\n", encoding="utf-8")
        git(work, "add", "aws-old.txt")
        git(work, "commit", "-m", "aws old")

        git(work, "checkout", "-b", "release/12.4.0.3")
        (work / "aws-new.txt").write_text("aws new\n", encoding="utf-8")
        git(work, "add", "aws-new.txt")
        git(work, "commit", "-m", "aws new")

        git(work, "checkout", "release/12.4.0.2")
        git(work, "checkout", "-b", "release/26.4.0.2")
        (work / "oci-old.txt").write_text("oci old\n", encoding="utf-8")
        git(work, "add", "oci-old.txt")
        git(work, "commit", "-m", "oci old")

        git(work, "checkout", "-b", "release/26.4.0.3")
        if not drift:
            git(work, "merge", "--no-edit", "release/12.4.0.3")
        (work / "oci-new.txt").write_text("oci new\n", encoding="utf-8")
        git(work, "add", "oci-new.txt")
        git(work, "commit", "-m", "oci new")

        git(work, "remote", "add", "origin", str(remote))
        git(work, "push", "origin", "release/12.4.0.2")
        git(work, "push", "origin", "release/12.4.0.3")
        git(work, "push", "origin", "release/26.4.0.2")
        git(work, "push", "origin", "release/26.4.0.3")
        return remote


if __name__ == "__main__":
    unittest.main()
