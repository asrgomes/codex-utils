# Falcon Jenkins API

Use `scripts/jenkins_build.py` for API reads when possible. It uses Jenkins JSON APIs, basic auth with the Oracle email and `FALCON_JENKINS_TOKEN`, progressive console offsets, bounded evidence downloads, redacted JSON output, and optional retries for transient Jenkins errors.

## Authentication

- Username: the user's Oracle email.
- Token: read only from `FALCON_JENKINS_TOKEN` unless the user explicitly chooses another `--token-env`.
- Never print the token, commit it, or include it in shell history. Helper output, saved Jenkins JSON, and saved console text are redacted; downloaded artifacts are raw Jenkins artifacts and should stay local under `/tmp`.

## URL Shapes

Jenkins job URLs use `/job/<segment>` pairs:

```text
https://hed.sfp.ocs.oc-test.com/falcon/job/folder/job/pipeline/job/branch
https://hed.sfp.ocs.oc-test.com/falcon/job/folder/job/pipeline/job/branch/123
```

Prefer full URLs for multibranch jobs whose branch names contain `/`. Jenkins usually double-encodes branch slashes in URL segments, so `feature/foo` may appear as `feature%252Ffoo`.

## Endpoints

- Job JSON: `<job-url>/api/json`
- Build JSON: `<build-url>/api/json`
- Latest build: `<job-url>/api/json?tree=lastBuild[number,url,result,building,timestamp,duration]`
- Recent builds: `<job-url>/api/json?tree=builds[number,url,result,building,timestamp,duration]{0,N}`
- Test report: `<build-url>/testReport/api/json`
- Artifact: `<build-url>/artifact/<relativePath>`
- Progressive console: `<build-url>/logText/progressiveText?start=<offset>`

When using `curl`, pass `--globoff` for Jenkins `tree=` queries because the query contains brackets.

## Retries And Limits

Use `--retries N` for transient Jenkins HTTP 429/5xx or network failures. Do not retry 401/403 authentication failures as if they were transient. `download-failure` applies artifact count, per-artifact byte, and total artifact byte limits; set `--max-artifacts 0` when JSON, console, and test reports are enough.

## Polling

Poll build JSON until `building` is false. Start around 10 seconds and grow toward 60 seconds unless the user needs a faster read. During waits, read progressive console text with the last `X-Text-Size` header as the next `start` value. Treat `X-More-Data: true` as "more console is available."

After pushing, prefer `wait-current-head` over a plain latest-build wait. It scans recent builds for the local branch and exact `git rev-parse HEAD`, then waits for the matching build to finish, so a stale latest green build cannot satisfy the goal.

## Branch And SHA Extraction

Prefer explicit build metadata over console text:

1. Build parameters such as `BRANCH_NAME`, `GIT_BRANCH`, `CHANGE_BRANCH`, `GIT_COMMIT`, `COMMIT_SHA`, `ghprbActualCommit`, and `GERRIT_PATCHSET_REVISION`.
2. Jenkins action metadata such as `lastBuiltRevision.SHA1`.
3. `changeSet.items[].commitId`.
4. Console lines like `Checking out Revision <sha> (origin/<branch>)`.
5. The final `/job/<segment>` as a weak branch hint for multibranch jobs.

Always compare the Jenkins branch and SHA with the local branch and `git rev-parse HEAD`. Jenkins console output often contains Pipeline library checkouts before the repository checkout; when multiple SHAs appear, prefer the SHA paired with the target repository branch over an earlier library SHA. Ask before proceeding if the mismatch changes which branch or commit should be fixed.

The helper returns branch extraction `confidence` and `warnings`. Treat `high` confidence as a matched branch/SHA pair. Treat `missing_branch`, `missing_sha`, `multiple_branch_candidates`, `multiple_sha_candidates`, and `no_branch_sha_pair_for_target_branch` as reasons to inspect console evidence or ask before editing.
