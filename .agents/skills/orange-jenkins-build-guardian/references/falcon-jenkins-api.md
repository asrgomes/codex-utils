# Falcon Jenkins API

Use `scripts/jenkins_build.py` for API reads when possible. It uses Jenkins JSON APIs, basic auth with the Oracle email and `FALCON_JENKINS_TOKEN`, progressive console offsets, and JSON output.

## Authentication

- Username: the user's Oracle email.
- Token: read only from `FALCON_JENKINS_TOKEN` unless the user explicitly chooses another `--token-env`.
- Never print the token, write it to evidence files, commit it, or include it in shell history.

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
- Test report: `<build-url>/testReport/api/json`
- Artifact: `<build-url>/artifact/<relativePath>`
- Progressive console: `<build-url>/logText/progressiveText?start=<offset>`

When using `curl`, pass `--globoff` for Jenkins `tree=` queries because the query contains brackets.

## Polling

Poll build JSON until `building` is false. Start around 10 seconds and grow toward 60 seconds unless the user needs a faster read. During waits, read progressive console text with the last `X-Text-Size` header as the next `start` value. Treat `X-More-Data: true` as "more console is available."

## Branch And SHA Extraction

Prefer explicit build metadata over console text:

1. Build parameters such as `BRANCH_NAME`, `GIT_BRANCH`, `CHANGE_BRANCH`, `GIT_COMMIT`, `COMMIT_SHA`, `ghprbActualCommit`, and `GERRIT_PATCHSET_REVISION`.
2. Jenkins action metadata such as `lastBuiltRevision.SHA1`.
3. `changeSet.items[].commitId`.
4. Console lines like `Checking out Revision <sha> (origin/<branch>)`.
5. The final `/job/<segment>` as a weak branch hint for multibranch jobs.

Always compare the Jenkins branch and SHA with the local branch and `git rev-parse HEAD`. Ask before proceeding if the mismatch changes which branch or commit should be fixed.
