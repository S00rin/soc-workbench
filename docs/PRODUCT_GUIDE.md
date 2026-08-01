# SOC Workbench product guide

## Appearance and navigation

The main navigation is on the right. **About Sorin** is the first menu section,
so the product introduction is always easy to find. On a small screen the menu
opens from the right and closes after navigation.

Use **Light** or **Dark** in the top bar to change the color theme. The selected
theme is stored in the browser and restored on the next visit.

## Analyzer Hub

Analyzer Hub brings connected services into one guided workspace:

1. **Connect** — configure Jira, Confluence, Wiki.js, or Splunk and test access.
2. **Analyze** — choose the permitted connection and ask a focused question.
3. **Review** — inspect the generated read-only query, result, and redacted history.

Connection credentials stay encrypted. Available tabs and actions follow the
signed-in user's module permissions and feature policies.

## Audit Log

Administrators can open **Audit Log** directly from the System menu, or select
the Audit Log tab in **Access & Features**. Product requests create tenant-scoped
events containing the user, module, action, outcome, duration, and full trace ID.

Filter events by user, module, action, or outcome. **Export CSV** downloads the
filtered view for review or retention. Requests that read or export the audit
log are excluded from audit generation to prevent recursive records.

## Administrator checklist

- Replace the initial administrator password and `SECRET_KEY` before deployment.
- Grant users only the modules they need.
- Set feature start/expiry windows where temporary access is required.
- Configure and test connections before enabling Sorin workflows.
- Use a trace ID to correlate a product action with server logs.
