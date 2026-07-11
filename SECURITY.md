# Security

SOC Workbench is a **single-user, self-hosted** tool intended to run on a
trusted host under the control of one analyst. Please read this before exposing
it beyond `localhost`.

## Hardening checklist before non-local use

- [ ] Set a strong, unique `SECRET_KEY` (used for JWT signing **and** for
      encrypting stored secrets and the tokenization map). Rotating it
      invalidates existing tokens and makes previously encrypted values
      unrecoverable.
      ```bash
      python -c "import secrets; print(secrets.token_urlsafe(48))"
      ```
- [ ] Change `ADMIN_USERNAME` / `ADMIN_PASSWORD` from the defaults.
- [ ] Set `ENVIRONMENT=production` and `DEBUG=false`.
- [ ] Restrict `CORS_ORIGINS` to the exact origin(s) you serve from.
- [ ] Terminate TLS in front of the app (reverse proxy); do not serve plain
      HTTP over an untrusted network.
- [ ] Protect the `data/` directory — it contains the SQLite database,
      uploaded documents, and the encrypted secret store.

## Secrets handling

- All secrets are supplied via environment variables / `.env`. The `.env` file
  is git-ignored — **never commit it**. Use `.env.example` as the template.
- Integration credentials and API keys entered through the Settings UI are
  encrypted at rest using `SECRET_KEY` before being stored in the database.
- Sensitive strings extracted from documents can be tokenized; the reversible
  mapping is likewise encrypted at rest.

## Reporting a vulnerability

This is a personal/internal project. If you discover a security issue, please
open a private report to the repository owner rather than filing a public
issue.

## Scope & intended use

This tool is designed for **authorized** security operations and analysis on
data you are permitted to handle. It is not hardened for multi-tenant or
public-internet deployment.
