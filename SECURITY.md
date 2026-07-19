# Security

SOC Workbench is a **self-hosted** tool with local database users and module
RBAC. It is intended to run on a trusted host under organizational control.
Please read this before exposing it beyond `localhost`.

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
- [ ] Review users, module permissions and feature expiry policies under
      **Access & Features**; deactivate bootstrap accounts that are not needed.
- [ ] Put an identity-aware reverse proxy in front of the app when enterprise
      SSO, MFA or centralized session revocation is required.

## Secrets handling

- All secrets are supplied via environment variables / `.env`. The `.env` file
  is git-ignored — **never commit it**. Use `.env.example` as the template.
- Integration credentials and API keys entered through the Settings UI are
  encrypted at rest using `SECRET_KEY` before being stored in the database.
- Sensitive strings extracted from documents can be tokenized; the reversible
  mapping is likewise encrypted at rest.
- User passwords are salted `scrypt` hashes. Login failures are rate-limited in
  the application process and passwords/request bodies are not written to the
  activity log.

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

The governance, Wiki.js, Atlassian and chat schemas carry tenant/owner
identifiers and enforce them in API queries. Module and feature authorization
is enforced by backend middleware; frontend menu hiding is not treated as an
authorization boundary. Legacy content tables predate multi-tenant support, so
a public SaaS/multi-tenant deployment still requires an external identity
provider, MFA, distributed rate limiting and broader tenant-isolation review.

## Wiki.js and connector chat controls

- Wiki.js API tokens are encrypted with `SECRET_KEY` and sent only as Bearer
  authorization to the configured `/graphql` endpoint.
- GraphQL documents are fixed by the provider; user search text is never
  concatenated into an executable GraphQL document.
- Jira, Confluence, Wiki.js and Splunk prompts and source content are untrusted
  LLM context. Output is redacted before persistence and sanitized before HTML
  rendering.
- Disabling AI globally or on a connection prevents that connection's content
  from being sent to the model. Provider queries remain read-only and bounded.

## Reporting a vulnerability

This is a personal/internal project. If you discover a security issue, please
open a private report to the repository owner rather than filing a public
issue.

## Scope & intended use

This tool is designed for **authorized** security operations and analysis on
data you are permitted to handle. It is not hardened for multi-tenant or
public-internet deployment.
