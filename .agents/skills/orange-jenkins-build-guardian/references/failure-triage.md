# Failure Triage

Classify before editing. Use `download-failure` to collect evidence and `classify` to get the first pass, then verify the classification against the console, test report, artifacts, and local source.

## Common Classes

- `test_failure`: failing JUnit/TestNG/Surefire/Failsafe tests, Mockito errors, assertion failures, or explicit test report failures.
- `compilation`: Java compiler failures, missing symbols, type errors, annotation processor errors.
- `static_analysis`: Checker Framework, SpotBugs, Checkstyle, PMD, lint, or formatting gates.
- `dependency_resolution`: Maven/Gradle cannot resolve or transfer artifacts.
- `scm`: checkout, branch resolution, git fetch, or missing revision failures.
- `timeout`: Jenkins timeout wrappers, stalled tests, or service waits.
- `infrastructure`: offline agents, workspace disk pressure, channel closures, pod provisioning, or network-only failures.
- `auth`: 401, 403, permission denied, or expired credential behavior.

Infrastructure, auth, SCM, dependency transfer, and timeout failures often need user confirmation or a rerun unless local evidence shows an application bug.

## Local Reproduction

Reproduce with the narrowest useful command:

- Single test method before full module test.
- Module-scoped Maven before repository-wide Maven.
- Static analysis target before full package.
- Exact profile or environment flags from Jenkins if visible.

Ask before starting databases, app servers, external services, or credential-dependent jobs. If local reproduction is impossible, only edit from Jenkins evidence when the root cause is direct and low-risk, such as a compile error pointing to one line.

## Mockito Matcher Failure

For `InvalidUseOfMatchersException`, `Misplaced or misused argument matcher`, or "matchers expected" failures, inspect the failing test for mixed raw values and matchers, matcher calls outside stubbing/verification, or final/private method stubbing. Prefer correcting test stubbing/verification to weakening production behavior.

## Do Not Paper Over Failures

Do not skip tests, loosen assertions, broaden trusted inputs, suppress exceptions, or remove validation to make Jenkins green. If the test expectation itself appears wrong, ask before changing it unless existing behavior/specs make the correction obvious.
