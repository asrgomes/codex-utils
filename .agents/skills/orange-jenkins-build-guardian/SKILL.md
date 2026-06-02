---
name: orange-jenkins-build-guardian
description: "Use for Orange/Falcon Jenkins build guarding: resolving Jenkins job or build URLs, aligning Jenkins branch and commit SHA with the local checkout, monitoring running builds, collecting failure evidence, triaging failures, reproducing and fixing locally, pushing, and repeating until the expected commit is green on the expected branch. Trigger when the user asks Codex to watch, debug, fix, rerun, or get a Falcon Jenkins build passing."
---

# Orange Jenkins Build Guardian

Use this skill to drive a Falcon Jenkins build from "which build?" to "the expected commit is green." Move quickly when evidence is clear, but stop for user input before risky state changes, unclear root causes, or security-relevant fixes.

## Start Gate

Require enough build identity before doing Jenkins work:

- If no Jenkins job name, branch URL, or build URL is available, ask for one.
- If the Jenkins username is unknown, ask for the user's Oracle email.
- Check that `FALCON_JENKINS_TOKEN` is set without printing it. If it is missing, ask the user to provide it in the environment.
- Resolve omitted build numbers through the Jenkins API before assuming which build matters.

Use `scripts/jenkins_build.py` for Jenkins API reads. Prefer it over hand-written `curl`; if using `curl` for a `tree=` query, use `curl --globoff`.

## Operating Loop

1. Normalize the job/build input and resolve the latest build if needed.
2. Extract Jenkins branch and build SHA, then compare them with the local branch and `HEAD`.
3. Ask before switching branches, creating worktrees, or continuing from a mismatched branch.
4. If the build is running, wait with adaptive polling and progressive console reads.
5. If the build failed, collect evidence in `/tmp`, including job JSON, build JSON, test report, console text, and artifacts.
6. Classify the failure before editing.
7. Reproduce locally with the narrowest useful command.
8. Ask if reproduction requires starting a DB/service, using new credentials, or leaving the sandbox.
9. Fix only when the root cause is clear from local reproduction or strong Jenkins evidence.
10. Review the proposed change for likely security regressions before committing.
11. Verify locally, run `git diff --check`, commit only intended changes, and push.
12. Wait for the next Jenkins build for the pushed SHA.
13. Repeat until Jenkins reports `SUCCESS` for the expected branch and commit SHA.

Never declare success until both Jenkins result and expected commit SHA match.

## Ask Gates

Ask the user before proceeding when any of these are true:

- Jenkins job/build input is missing, ambiguous, or has multiple plausible matches.
- Jenkins username/email is unknown.
- Local branch differs from Jenkins branch.
- Jenkins build SHA differs from local `HEAD` and the next step is unclear.
- Unrelated dirty changes overlap files that need edits.
- A destructive git action, branch switch, or new worktree is needed.
- Local reproduction requires a DB, service, external credentials, or environment setup not already available.
- The failure appears environmental or infrastructure-related.
- Evidence leaves multiple plausible root causes.
- The fix implies major refactoring, deleting code, broad shared-code changes, public API changes, product behavior changes, or test expectation changes.
- The fix weakens validation, authentication, authorization, sanitization, escaping, encryption, logging safety, or error handling.
- The fix suppresses, skips, or loosens tests instead of addressing the underlying failure.
- A commit message or ticket association is not inferable.
- Jenkins repeatedly fails for different reasons and the loop is no longer converging.

## Safety Rules

Do not print or persist Jenkins tokens. Do not write Jenkins evidence into tracked repo paths. Do not use destructive git commands without explicit user approval.

Before committing, check the diff for likely security regressions. In particular, avoid hardcoded secrets, sensitive-data logging, weakened authz/authn, removed validation or escaping, command injection, SQL injection, SSRF, path traversal, unsafe deserialization, XSS, XXE, insecure reflection/scripting, and broader exception swallowing that hides security failures. If a security-relevant change is unavoidable, stop and ask the user to confirm the intended direction.

## References

- Load [falcon-jenkins-api.md](references/falcon-jenkins-api.md) for Jenkins API endpoints, auth, polling, progressive console reads, branch parsing, and SHA extraction.
- Load [codex-operating-loop.md](references/codex-operating-loop.md) for Codex tool usage, git safety, sandbox escalation, and when to ask.
- Load [failure-triage.md](references/failure-triage.md) before classifying failures or choosing local reproduction commands.
- Load [security-safety.md](references/security-safety.md) before editing or committing security-sensitive code paths.

## Helper

Run:

```bash
python <skill-dir>/scripts/jenkins_build.py --help
```

Common commands:

```bash
python <skill-dir>/scripts/jenkins_build.py normalize --job-url "$BUILD_URL" --json
python <skill-dir>/scripts/jenkins_build.py status --job-url "$BUILD_URL" --username "$ORACLE_EMAIL" --json
python <skill-dir>/scripts/jenkins_build.py wait --job-url "$JOB_URL" --build "$BUILD" --username "$ORACLE_EMAIL" --json
python <skill-dir>/scripts/jenkins_build.py download-failure --job-url "$BUILD_URL" --username "$ORACLE_EMAIL" --json
python <skill-dir>/scripts/jenkins_build.py classify --evidence-dir /tmp/orange-jenkins-build-guardian/<case> --json
```

When changing the helper, run:

```bash
python -m unittest discover <skill-dir>/tests
```
