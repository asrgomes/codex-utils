# SFP Release Drift Audit

This directory contains the release-branch drift checker used by the central Jenkins job for SFP repositories.

The checker audits configured ALM Git repositories and reports when release branches are no longer carrying the commits they are expected to contain. It is intentionally implemented as a small Python script plus a Jenkinsfile so the job can run with ordinary Jenkins agent tools: Python, Git, optional SSH credentials, and optional Slack notifications.

## Why This Tool Exists

SFP maintains paired AWS and OCI release branch lines. The branch names encode the release family and version:

- AWS release branches use `release/12.X.Y.Z`.
- OCI release branches use `release/26.X.Y.Z`.

For a matching version, OCI is expected to contain the corresponding AWS branch. Newer release branches in each family are also expected to contain the previous selected release branch. If a commit is present in an older or source release branch but missing from the branch that should contain it, later fixes, merge-request metadata, or release-critical changes can silently disappear from the active line.

This tool exists to make that drift visible quickly:

- It checks all configured repositories the same way on every run.
- It fails the Jenkins build when material release drift is found.
- It writes an archived Markdown report with branch and commit details.
- It can write a compact Slack alert body for failed Jenkins runs.
- It can ignore branch-pair drift when a simulated source-into-target merge would not change the target branch files.
- It can suppress known violations for explicitly configured target branches while keeping the rest of the audit active.

The checker uses Git ancestry and commit identity, not patch equivalence. A cherry-picked commit with a different SHA is still reported as missing, even if the file content looks equivalent.

## What It Checks

For each configured repository, the checker fetches remote release branches and validates three containment rules.

AWS-to-OCI containment:

- `release/26.X.Y.Z` must contain `release/12.X.Y.Z` for matching `X.Y.Z` versions.
- If the matching OCI branch does not exist, the audit fails with a missing-branch finding.

Adjacent AWS containment:

- For the selected AWS releases, each newer selected `release/12...` branch must contain the previous selected `release/12...` branch.

Adjacent OCI containment:

- For the selected OCI releases, each newer selected `release/26...` branch must contain the previous selected `release/26...` branch.

Pending commits are found with this Git range:

```bash
git log origin/<TO_BRANCH>..origin/<FROM_BRANCH>
```

That means "commits present in `<FROM_BRANCH>` but not reachable from `<TO_BRANCH>`."

## Branch Selection

Only remote branches matching these patterns are considered:

- `release/12.<number>.<number>.<number>`
- `release/26.<number>.<number>.<number>`

Branches are parsed numerically and sorted newest first. For example, `release/12.10.0.0` sorts after `release/12.4.1.0`.

`max_versions` controls how many branches are selected per family. With `max_versions = 5`, the checker selects the newest five AWS release branches and the newest five OCI release branches in each repository.

Remote branch fetching is scoped to release branches:

```bash
git fetch --prune origin '+refs/heads/release/*:refs/remotes/origin/release/*'
```

## Non-Material Commit Ignore Mode

Some commits can show up as ancestry drift even though merging the source branch into the target branch would not change any target files.

Set this option to enable the ignore behavior:

```toml
ignore_non_material_commits = true
```

A branch-pair drift finding is ignored only when Git can cleanly simulate merging the source branch into the target branch and the resulting tree is identical to the current target branch tree:

- The checker runs `git merge-tree --write-tree origin/<target> origin/<source>`.
- The simulated merge must complete successfully.
- The command output must be one valid Git tree hash.
- That tree hash must equal `origin/<target>^{tree}`.

Merge-request subject text is not required. If the simulated merge conflicts, fails, or returns malformed output, the branch-pair drift remains material and can fail the audit.

When a branch-pair merge is non-material, all pending commits for that branch pair are ignored. Ignored commits do not create `commit_drift` findings and do not affect report status. They are not listed in Markdown or Slack report output.

## Suppressed Branches

Use `suppressed_branches` when a known branch-specific violation should not fail the audit yet, but the repository should otherwise keep being checked.

Example:

```toml
suppressed_branches = ["release/26.4.1.0"]
```

Suppression is applied to the target branch of a check:

- AWS-to-OCI drift for `release/12.4.1.0` into `release/26.4.1.0` is suppressed when `release/26.4.1.0` is listed.
- Adjacent OCI drift detected in `release/26.4.1.0` is suppressed when `release/26.4.1.0` is listed.
- Missing-branch findings are suppressed when the missing target branch is listed.

Suppression is not repository-specific. A branch name listed here is suppressed in every configured repository where that target branch would otherwise produce a finding.

Suppressed target branches do not create findings and do not affect report status. Suppressed branch names and suppressed violations are not listed in Markdown or Slack report output.

## Configuration

Configure the checker with a TOML file. The checked-in file is [config.toml](config.toml).

Run the script with `-f`; there is no default config path:

```bash
python3.12 jenkins/sfp-release-drift/scripts/sfp_release_drift.py \
  -f jenkins/sfp-release-drift/config.toml
```

### Example Config

```toml
verbose = true
tmp_dir = "/tmp/drift"
max_versions = 5
ignore_non_material_commits = true
suppressed_branches = []

repositories = [
    "ssh://alm.oraclecorp.com/sfp_vm_24182/mpg.git",
    "ssh://alm.oraclecorp.com/sfp_vm_24182/vm.git",
]

output_report_file = "drift-report.md"
slack_text_file = "drift-report-slack.txt"
```

### Config Keys

`verbose`

- Required boolean.
- `true` enables detailed progress logs for repository URLs, work directories, fetched branch counts, selected branches, and individual drift checks.
- `false` keeps progress output shorter.

`tmp_dir`

- Required non-empty string.
- Directory used for local Git working copies.
- The checker creates one stable subdirectory per configured repository.
- Existing working directories are reused across runs; `origin` is added or updated as needed.
- Relative paths are resolved relative to the TOML config file directory.
- For Jenkins, an absolute path such as `/tmp/drift` avoids writing clone data into the workspace.

`max_versions`

- Required positive integer.
- Number of newest release branches to check per family, not total.
- With `max_versions = 5`, up to five AWS branches and up to five OCI branches are selected per repository.
- Boolean values are rejected even though TOML booleans are technically integer-like in Python.

`ignore_non_material_commits`

- Optional boolean.
- Defaults to `false` when omitted.
- When `true`, enables the branch-pair no-op merge ignore behavior described above.
- Non-boolean values are rejected.

`suppressed_branches`

- Optional list of non-empty strings.
- Defaults to `[]` when omitted.
- Each value is a target branch name whose drift findings should be suppressed.
- Example: `suppressed_branches = ["release/26.4.1.0"]`.
- Applies globally across every configured repository.
- Non-list values and blank/non-string entries are rejected.

`repositories`

- Required non-empty list of non-empty strings.
- Every entry must be an `ssh://` URL.
- HTTPS URLs and SCP-like Git syntax are rejected by config validation.
- The typo `repsitories` is detected and reported with a correction hint.

`output_report_file`

- Required non-empty string.
- Must end with `.md`.
- The Markdown report path.
- Relative paths are resolved relative to the TOML config file directory.
- Parent directories are created automatically.

`slack_text_file`

- Optional non-empty string.
- Compact Slack summary text file used by the Jenkinsfile on failures.
- Relative paths are resolved relative to the TOML config file directory.
- Parent directories are created automatically.

## Output

The script writes progress logs to stderr and the report artifacts configured in TOML.

Markdown report:

- Generated timestamp.
- Overall status: `pass` or `fail`.
- Scanned AWS and OCI branch lists, excluding suppressed branch names.
- Configuration findings, if config or environment setup failed.
- Repository drift sections grouped by repository and target branch.
- Missing commit labels as short hash plus subject.
- Only material, unsuppressed findings.

Slack text:

- Pass text when no material drift is found.
- Failure summary with finding count.
- Up to 20 findings.
- Up to 10 commits per finding by default.
- Hidden commit and finding counts when the archived report contains more detail.
- Only material, unsuppressed findings.

Completion logs:

- Clean runs say no missing commits were found.
- Failed drift runs report the number of repositories with branch drift.
- Non-drift failures, such as config or Git setup failures, are reported separately.

## Exit Status

The script exits with:

- `0` when no material findings exist.
- `1` when configuration validation fails, Git setup fails, fetch/drift checks fail, a required branch is missing, or material commit drift is found.

Ignored non-material commits do not change a passing status to failing.

Suppressed target-branch violations also do not change a passing status to failing.

## Jenkins Usage

The checked-in [Jenkinsfile](Jenkinsfile) runs the checker hourly:

```groovy
cron('H * * * *')
```

It defines these parameters:

`ALM_GIT_CREDENTIALS_ID`

- Optional Jenkins SSH credential id.
- When provided, the audit command runs inside `sshagent`.
- Leave blank when the Jenkins agent already has access to the configured repositories.

`SLACK_CHANNEL`

- Optional Slack channel for failed drift alerts.
- When blank, the build still fails on drift, but no Slack message is sent.

The Jenkinsfile removes old report artifacts at the start of the audit, runs:

```bash
python3.12 jenkins/sfp-release-drift/scripts/sfp_release_drift.py \
  -f jenkins/sfp-release-drift/config.toml
```

On failure, it reads `drift-report-slack.txt`, appends the Jenkins build URL when available, optionally sends it through `slackSend`, and then fails the build.

The job always archives:

- `jenkins/sfp-release-drift/drift-report.md`
- `jenkins/sfp-release-drift/drift-report-slack.txt`

The Jenkinsfile does not create jobs, modify Jenkins server configuration, call Jenkins REST APIs, or manage credentials. Jenkins job setup remains the responsibility of the Jenkins owner.

## Local Usage

From the repository root that contains `jenkins/sfp-release-drift`:

```bash
python3.12 jenkins/sfp-release-drift/scripts/sfp_release_drift.py \
  -f jenkins/sfp-release-drift/config.toml
```

From inside this directory:

```bash
python3.12 scripts/sfp_release_drift.py -f config.toml
```

Run unit tests:

```bash
python3.12 -m unittest discover -s tests
```

Run the full local verification set used while maintaining this tool:

```bash
python3.12 -m unittest discover -s tests
python3.12 -m mypy scripts/sfp_release_drift.py tests/test_sfp_release_drift.py
python3.12 -m py_compile scripts/sfp_release_drift.py tests/test_sfp_release_drift.py
/home/antonio/.pyenv/versions/3.13.5/bin/ruff check \
  scripts/sfp_release_drift.py tests/test_sfp_release_drift.py
```

## Requirements

- Python 3.12 or newer.
- Git on `PATH`.
- Network and SSH access to all configured repositories.
- Jenkins Slack plugin only if Slack alerts are desired.
- Jenkins SSH Agent plugin only if `ALM_GIT_CREDENTIALS_ID` is used.

## Logging

Progress logs are written to stderr with fixed-width severity labels:

- `INFO`
- `DEBUG`
- `WARN`
- `ERROR`

When stderr is an interactive terminal with ANSI color support:

- `DEBUG` is dim gray.
- `WARN` is yellow.
- `ERROR` is bold red.
- `INFO` stays in the default terminal color.

Colors are disabled for redirected output, `TERM=dumb`, or when `NO_COLOR` is set. `FORCE_COLOR` enables colors.

## Troubleshooting

Config file not found:

- Confirm the `-f` path is correct.
- The script does not search for a default config file.

Repository URL rejected:

- Use `ssh://...` URLs.
- HTTPS URLs and SCP-like syntax are rejected by design.

Missing release branches:

- Confirm the repository has branches matching `release/12.X.Y.Z` or `release/26.X.Y.Z`.
- Branch names outside those exact patterns are ignored.

Unexpected drift for cherry-picks:

- This is expected. The audit uses commit reachability, not patch equivalence.
- A cherry-pick with a new SHA is a different commit and remains drift until the expected commit is reachable from the target branch or the release strategy is adjusted.

Ignored non-material commits do not appear in the report:

- This is intentional. When `ignore_non_material_commits = true`, branch-pair no-op merge drift is filtered out of report artifacts.

Expected no-op branch-pair drift still fails:

- Confirm `ignore_non_material_commits = true`.
- Confirm `git merge-tree --write-tree origin/<target> origin/<source>` completes cleanly.
- Confirm the simulated merge tree equals `origin/<target>^{tree}`.
- If the simulated merge changes files, conflicts, fails, or returns malformed output, the drift is material and should fail.

Expected branch drift still fails after adding `suppressed_branches`:

- Confirm the target branch, not the source branch, is listed.
- For AWS-to-OCI drift, list the OCI branch such as `release/26.4.1.0`.
- For adjacent drift, list the newer branch where drift is detected.
- Suppression applies to exact branch-name matches only.

Fetch failures:

- Confirm Jenkins or the local shell has SSH access to every configured repository.
- If Jenkins credentials are needed, set `ALM_GIT_CREDENTIALS_ID`.

Report file missing:

- On config-load failures, Markdown is written to stdout because output paths may not be valid yet.
- In Jenkins, archived artifacts are allowed to be empty so failed setup does not hide the console log.
