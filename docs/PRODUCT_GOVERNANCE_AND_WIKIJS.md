# Product governance, integration chat and Wiki.js

## What changed

SOC Workbench now has a database-backed access layer in front of the existing
modules. The initial `.env` administrator is migrated non-destructively into
`user_accounts`; subsequent users, module permissions and feature policies are
managed from **Access & Features**.

The compact product navigation groups related screens into these hubs:

- **Data & IoCs**: processing, knowledge, indicators and projects.
- **Integration Hub**: shared prompt chat, Jira/Confluence administration,
  Wiki.js and Splunk.
- **Intelligence**: internet intelligence and automation.
- **Operations**: jobs and notifications.

Old frontend URLs remain as redirects so bookmarks do not break. Existing Jira
settings, Atlassian connections, mappings and history are not deleted.

## Users and module access

Administrators can create `viewer`, `analyst` and `admin` accounts. Viewers and
analysts receive an explicit list of modules. Admins always receive every
module so an accidental UI edit cannot strand the deployment without an
administrator.

Passwords use salted `scrypt` hashes. Temporary passwords must contain at least
12 characters and can require a change after sign-in. Login failures are
rate-limited per username and client address. Active-user and permission state
is loaded from the database for every API request, so deactivation takes effect
without waiting for the JWT to expire.

Frontend menu hiding is only a convenience. The backend middleware enforces
the same module rules and records mutating actions in `user_activity` without
capturing request bodies or secrets.

## Feature start and expiry

Each feature policy has:

- an explicit enabled switch;
- optional start and expiry timestamps;
- an optional allow-list of roles;
- a JSON policy configuration reserved for provider-specific limits.

The admin UI includes 7, 30 and 90 day presets plus unlimited duration. An
expired or scheduled feature returns an actionable `403 feature_unavailable`
response from the backend. Provider policies are independent: Jira,
Confluence, Wiki.js, Splunk, integration chat, bulk operations and AI processing
can be scheduled separately.

Disabling **AI Processing** or disabling AI on a connection prevents connector
content and prompts from being sent to the configured model. Read-only fallback
search and deterministic summaries remain available where practical.

## Configure Wiki.js

Wiki.js v2.2 or later exposes an authenticated GraphQL API when **API Access**
is enabled. In Wiki.js:

1. Open **Administration → API Access** and enable API access.
2. Create a new API key with the group and expiry appropriate for this
   deployment.
3. Grant that group view permission for only the required pages/locales.
4. In SOC Workbench open **Integration Hub → Wiki.js → Add Wiki.js**.
5. Enter the Wiki.js base URL, paste the token once, keep TLS verification on,
   save, and run **Test & permissions**.

SOC Workbench sends the token as `Authorization: Bearer …` and automatically
uses the fixed `/graphql` endpoint. The token is Fernet-encrypted at rest and is
never returned to the browser. User text is passed as GraphQL variables or used
for local title/path ranking; it is never concatenated into a GraphQL document.

Official references:

- [Wiki.js GraphQL API](https://docs.requarks.io/dev/api)
- [Wiki.js GraphQL queries](https://docs.requarks.io/dev/api#queries)

## Shared prompt chat

The same conversation UI supports Jira, Confluence, Wiki.js and Splunk:

1. Select an enabled connection.
2. Write a natural-language request.
3. The backend creates a bounded read-only JQL, CQL, Wiki.js search, or SPL
   query and validates it before execution.
4. The generated query and result count can be expanded under the answer.
5. Continue with follow-up prompts, or choose **Edit & run again** to load an
   earlier prompt and query into the composer.

Every turn stores the redacted prompt, generated query, response, result
summary, provider/model, duration, status, error code and correlation ID. Chat
history is tenant- and owner-scoped. Jira and Confluence prompt turns are also
written into the existing Integration History so current export and retention
workflows continue to apply.

Issue and page content is treated as untrusted model context. The system prompt
forbids following instructions embedded in connector content, secrets are
redacted before persistence, result size is bounded and rendered Markdown is
sanitized against XSS.

## Migration and deployment

Migration `0002_product_governance` creates:

- `user_accounts`
- `feature_policies`
- `external_connections`
- `integration_chat_sessions`
- `integration_chat_turns`
- `user_activity`

Upgrade is automatic at application start, or can be run explicitly:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.migrations.runner upgrade
```

Recommended deployment order:

1. Stop the running application.
2. Back up `data/app.db` and `.env`.
3. Build the frontend with `npm run typecheck`, `npm test`, and `npm run build`.
4. Run backend tests and the migration command.
5. Start Uvicorn and verify `/api/health`, login, **Access & Features**, and each
   connection test.

Rollback of only this migration is available:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.migrations.runner downgrade 0002_product_governance
```

This drops the six governance/chat tables and is destructive to new users,
feature policies, Wiki.js connections and chat history. Restore the database
backup for a full rollback. It does not remove legacy Jira/Atlassian data.
