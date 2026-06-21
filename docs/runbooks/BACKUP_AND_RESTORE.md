# Backup and Restore

Stage 11A exercises backup and restore with synthetic local/test data only.

Drill:

1. create synthetic rows in a temporary drill directory
2. write a logical backup manifest
3. calculate SHA256
4. clear the in-memory source
5. restore from the manifest
6. compare row count and SHA256

PostgreSQL logical backup, MinIO/raw payload manifest backup, config/schema/model manifest backup,
and encrypted backup are represented as interfaces. No real encryption key is generated.

Point-in-time recovery remains a documented future production procedure.
