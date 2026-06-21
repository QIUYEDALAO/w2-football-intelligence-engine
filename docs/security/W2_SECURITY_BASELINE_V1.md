# W2 Security Baseline V1

Stage 11A establishes a scaffold only:

- roles: VIEWER, OPERATOR, ADMIN
- operations APIs remain read-only
- production operations stay disabled
- CORS is limited to local/staging origins
- rate-limit policy is an abstraction
- security headers are defined for deployment integration
- dependency vulnerability scanning is a local review placeholder
- audit events are structured and redacted

No real user management, production auth key, or external notification channel is introduced.
W2 must not read W1 credential paths.
