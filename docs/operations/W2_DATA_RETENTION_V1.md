# W2 Data Retention V1

Retention policy:

- raw payload retention uses manifests
- normalized and feature artifacts retain by dataset version
- replay and model artifacts retain by experiment manifest
- audit is retained permanently
- cache/log cleanup is dry-run only
- backup retention follows local/staging policy
- legal hold requires manual approval

Stage 15A deletes no files.
