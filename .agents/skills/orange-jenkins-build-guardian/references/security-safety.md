# Security Safety

Before committing any fix, inspect the diff for likely security regressions. Stop and ask if the intended fix is security-relevant and not clearly safe.

## Never Introduce

- Hardcoded secrets, tokens, cookies, passwords, private keys, or internal credentials.
- Logging of secrets, auth headers, sensitive student/customer data, or full payloads that may contain protected data.
- Weaker authentication, authorization, role checks, ownership checks, tenant checks, or entitlement checks.
- Removed input validation, output escaping, CSRF protection, SQL/query safety, path checks, or file-upload restrictions.
- Command injection, SQL injection, SSRF, path traversal, unsafe deserialization, XSS, XXE, unsafe reflection, or unsafe scripting.
- Exception swallowing that hides security failures or silently grants access.
- Test changes that disable security checks or broaden trusted input classes without product approval.

## Review Prompts

Ask these before commit:

- Did the fix change who can access data or actions?
- Did the fix trust new input, URLs, file paths, scripts, SQL, XML, HTML, or serialized data?
- Did the fix log or persist new data?
- Did the fix convert a failure into a silent success?
- Did the fix weaken a test that guards validation or access control?

If any answer is yes, either prove the change is safe from local context or ask the user to confirm the intended direction.
