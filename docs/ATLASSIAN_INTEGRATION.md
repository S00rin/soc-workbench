# Atlassian integration setup

The **Analyzer Hub → Jira & Confluence** page manages Jira and Confluence through one
shared, encrypted connection model. A connection may enable Jira, Confluence,
or both products when the same Atlassian site and credential has the required
access.

## Choose an authentication method

### Jira/Confluence Cloud API token

Use this for a simple self-hosted installation:

1. Create an API token for a dedicated Atlassian service account.
2. Add a connection with deployment **Cloud** and authentication **Cloud API
   token**.
3. Set Base URL to `https://your-site.atlassian.net`, enter the service-account
   email, and paste the token once.
4. Save, then run **Test & permissions**. The UI reports authentication, issue
   read/search, field metadata, project browsing and comment capability
   separately.

The token only has the permissions of its Atlassian user. Project permission,
issue security and space restrictions continue to apply.

### Jira Data Center PAT

Choose deployment **Data Center** and authentication **PAT**, enter the Jira or
Confluence base URL, and paste a Personal Access Token. Basic authentication is
also available for installations that explicitly permit it. Prefer PAT over a
password, keep TLS verification enabled, and use a least-privileged service
account.

### Atlassian Cloud OAuth 2.0 (3LO)

Create an OAuth 2.0 integration in the Atlassian developer console and register
the exact callback URL. Configure:

```dotenv
ATLASSIAN_OAUTH_CLIENT_ID=your-client-id
ATLASSIAN_OAUTH_CLIENT_SECRET=your-client-secret
ATLASSIAN_OAUTH_REDIRECT_URI=https://workbench.example.com/api/atlassian/oauth/callback
```

Create and save an **OAuth 2.0 (3LO)** connection, then choose **Reconnect
OAuth**. Authorization state is signed and expires after ten minutes. Access
and rotating refresh tokens are encrypted at rest and refreshed automatically.

The built-in default scopes cover the current operations. When defining custom
scopes, grant only what is enabled in your deployment. Typical Jira granular or
classic equivalents must allow identity/access metadata, issue/project/field
read, search and comment write. Confluence must allow space/page/comment read
and footer-comment write. Atlassian changes scope names over time, so verify the
exact scopes against the linked official documentation before registering a
production app.

## Permission and error handling

**Test & permissions** performs side-effect-free capability probes wherever
Atlassian exposes them. Jira comment access is checked through `mypermissions`.
Confluence has no universal side-effect-free comment probe, so the UI reports
that capability as indeterminate until an approved post is attempted.

Errors are separated into invalid/expired token, insufficient scope or project
permission, not found/restricted content, conflict, rate limit, network and
temporary upstream failure. Only network, HTTP 429 and temporary 5xx responses
receive bounded exponential-backoff retries. Reauthorization is offered for an
expired OAuth connection; no permission bypass or impersonation exists.

## Jira field mapping

Open **Field mapping**, select connection/project/issue-type scope and refresh
metadata. Standard and custom fields are loaded from Jira. Required and
read-only metadata is validated, and a metadata hash marks removed or changed
fields as stale/invalid with an actionable warning.

Mappings can be created, edited, deleted, exported and imported. Supported
declarative transformations are `identity`, `stringify`, `number`,
`date_format`, `join`, `split`, `map_values`, `option`, `user`, `components`
and `adf`. No executable user code is accepted. **Preview** applies the effective
connection → project → issue-type precedence to sample internal data before it
is saved or used.

## SOC reports and KPI

Open **Analyzer Hub → Jira & Confluence → KPI**. The workspace includes
version-controlled prompts and JQL for daily operations, weekly performance,
monthly executive review and shift handover. Enter a Jira project key, choose
the report and set the resolution SLA target. The generated Markdown is ready
to download or copy into Confluence. Every execution records its JQL, redacted
prompt, outcome and correlation ID in Integration History and Audit Log.

The calculations cover issue volume, resolved/open backlog, resolution rate,
MTTR and median resolution time, SLA compliance, mean open age, high/critical
volume, assignment coverage, unassigned work, overdue issues and status/priority
distributions. Jira processing is capped at 500 issues per run; narrow the
project/time JQL when the reported Jira total is higher than the processed count.

MTTA and MTTD require organization-specific timestamps. Expand **Advanced KPI
field mapping** and enter the Jira custom field IDs containing acknowledgement
and detection/event times. When those fields or valid timestamps are absent,
the UI reports `N/A` and a data-quality reason instead of manufacturing a value.
MTTR uses Jira `created` and `resolutiondate`; SLA compliance compares resolved
duration with the selected target.

## Smart and bulk comments

Single-item comment generation reads the actual Jira issue or Confluence page
context and treats it as untrusted data. The suggested text is always visible
and editable. `Suggest only` never posts; `Require approval` requires a fresh
explicit confirmation; `Auto-post` works only when an admin enables it on the
connection.

Bulk jobs require a dry run and confirmation. Targets are bounded to selected
keys/IDs, JQL/CQL results, a project, a saved Jira filter or a Confluence space.
The worker persists per-item state, progress, failures and external comment IDs,
respects the admin maximum, skips configured statuses, detects duplicates and
uses idempotency keys for safe retry. Pause/resume/cancel state is persistent,
but workers run in the application process; after a process restart, resume a
pending/partial job from the UI.

## History, retention and privacy

JQL, CQL, prompts, target keys, outcome, duration, model/provider, result count,
error classification and correlation ID are stored in tenant-aware history.
Search, filter, details, clone/re-run, soft delete and JSON/CSV export are
available. Sensitive values are masked before persistence. Admin policy values
are stored under Settings; environment defaults are:

```dotenv
ATLASSIAN_HISTORY_RETENTION_DAYS=90
ATLASSIAN_BULK_MAX_ISSUES=100
```

Retention cleanup is available as a service policy hook. Schedule it with the
existing application scheduler when a hard automatic purge SLA is required.

## Migration, deployment and rollback

Back up `data/app.db` before deployment. Application startup runs the additive
`0001_atlassian_domain` migration automatically. It does not delete the legacy
Jira settings; on first startup, those settings are copied into an encrypted
Atlassian connection when possible.

For an explicit migration check:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.migrations.runner upgrade
```

Then build and validate:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
cd ..\frontend
npm run typecheck
npm test -- --run
npm run build
```

Restart the backend and open `/atlassian`. Test each connection before enabling
comment policies. A safe application rollback is to deploy the previous code
while leaving the additive tables in place. To remove the new schema entirely,
first export mappings/history, stop the application, back up the database, then
run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.migrations.runner downgrade 0001_atlassian_domain
```

Downgrade deletes Atlassian connection/mapping/history/bulk/audit tables and is
therefore destructive. Legacy Jira settings are not removed.

## Current operational limits

- Application login is database-backed and supports per-module roles. Atlassian
  connections and history remain tenant-scoped; chat history is also owner-scoped.
- Bulk execution uses the existing in-process worker pool rather than Redis or
  another external queue.
- Confluence page creation/update and inline comments are not enabled; the
  implementation currently supports search, page context and footer comments.
- Live Atlassian tests are optional and require environment-provided credentials;
  automated tests use mock transports and never require real tokens.

## Official references

- [Jira Cloud REST API v3](https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/)
- [Jira Cloud OAuth 2.0 (3LO)](https://developer.atlassian.com/cloud/jira/platform/oauth-2-3lo-apps/)
- [Jira Cloud issue comments](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-comments/)
- [Jira Data Center REST authentication](https://developer.atlassian.com/server/jira/platform/basic-authentication/)
- [Confluence Cloud REST API v2](https://developer.atlassian.com/cloud/confluence/rest/v2/intro/)
- [Confluence Cloud OAuth 2.0 (3LO)](https://developer.atlassian.com/cloud/confluence/oauth-2-3lo-apps/)
- [Confluence Data Center OAuth provider](https://developer.atlassian.com/server/confluence/confluence-oauth2-provider-api/)
