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

## Atlassian security controls

- Jira/Confluence API tokens, PATs, passwords, OAuth access tokens and rotating
  refresh tokens are encrypted with `SECRET_KEY`; API responses never return
  credential material.
- History is tenant- and user-scoped. Prompts, JQL/CQL, results and errors pass
  through secret-pattern redaction and the existing sensitive-data masker.
- Jira and Confluence content is treated as untrusted context for the LLM.
  Embedded instructions cannot change approval, RBAC, auto-post or bulk policy.
- Auto-post is disabled by default. Bulk posting requires an admin role, dry
  run, exact target count, explicit confirmation, a configured ceiling,
  per-target idempotency and audit records.
- Retry is limited to network failures, rate limiting and temporary 5xx errors;
  authentication and permission failures are not blindly retried.
- `VERIFY_SSL` should remain enabled. HTTP endpoints are supported only for
  explicitly configured private Data Center development environments.

The schema carries tenant and owner identifiers and enforces them in Atlassian
queries. The rest of the application still has a single configured login, so a
public multi-user deployment also needs an external identity provider, request
rate limiting and broader application-wide tenant isolation review.

## Reporting a vulnerability

This is a personal/internal project. If you discover a security issue, please
open a private report to the repository owner rather than filing a public
issue.

## Scope & intended use

This tool is designed for **authorized** security operations and analysis on
data you are permitted to handle. It is not hardened for multi-tenant or
public-internet deployment.
