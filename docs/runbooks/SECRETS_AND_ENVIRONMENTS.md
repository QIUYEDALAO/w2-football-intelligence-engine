# Secrets and Environments

Supported environments are `local`, `test`, `staging`, and `production`.
Configuration examples live in `config/environments/`.

Rules:

- API keys come only from environment variables or a future secret manager.
- `.env` files are ignored by Git.
- `.env.example` contains only obvious placeholder values.
- Logs must not print full environment variables, database passwords, tokens, or
  authorization headers.
- W2 must not read W1 or legacy project `.env` files.

Stage 2 keeps `real_recommendation_enabled: false` for every environment.

