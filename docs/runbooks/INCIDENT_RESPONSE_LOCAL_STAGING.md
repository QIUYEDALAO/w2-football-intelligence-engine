# Incident Response for Local and Staging

Stage 11A incidents are local/staging only.

Immediate stops:

- frozen manifest hash mismatch
- low quota
- provider 401/403/429
- DeepSeek enabled
- candidate or recommendation output
- backup verification failure
- W1 credential path access

External notification is disabled. Operators inspect `/metrics`, reports, structured logs, and local
alert records, then rerun the relevant checker after remediation.
