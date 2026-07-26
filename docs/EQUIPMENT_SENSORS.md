# Equipment & Sensor Library

A living catalog of every device and sensor the SOC operates, written for
analysts and log-onboarding engineers. Each entry answers four questions:

1. **What is it?** — vendor, model, category, criticality, an introduction, and
   the security capabilities it provides.
2. **What does it log?** — the distinct log/event streams it emits, with a
   sample event, key fields, the target SIEM sourcetype/index, an estimated
   EPS, retention, and the mapped MITRE ATT&CK data source.
3. **How do we collect it?** — step-by-step log-collection / onboarding guides.
4. **How do we respond?** — **runbooks** (operational procedures) and
   **playbooks** (incident-response procedures, with severity, trigger and
   ATT&CK techniques).

Any sensor profile — or an individual document — can be **published to
Confluence** through an existing Atlassian connection, so the catalog and the
team wiki stay in sync.

The UI is bilingual (English / Farsi) and available at **`/sensors`** under the
*Sensor Library* navigation item. It is gated by the `sensors` module in the
Access & Features admin.

## Data model

| Table | Purpose |
|-------|---------|
| `equipment_sensors` | The device/sensor: identity, category, criticality, capabilities (JSON), collection methods, tags, MITRE tactic coverage, and the last Confluence page it was published to. |
| `sensor_log_sources` | One row per log/event stream: format, sample, key fields, SIEM sourcetype/index, EPS estimate, retention, MITRE data source. |
| `sensor_documents` | Markdown documents of kind `overview`, `collection`, `onboarding`, `runbook`, `playbook` or `reference`. Playbooks additionally carry severity, trigger and ATT&CK techniques. |

All three are tenant-scoped. Migration `0006_equipment_sensors` creates them; a
startup seed inserts built-in reference sensors (idempotent, never overwrites
edits).

## API

Base path `/api/sensors`. Reads require the `sensors` module; mutations require
the administrator role. All write actions are recorded to the audit log.

| Method & path | Description |
|---------------|-------------|
| `GET /catalog` | Enumerations for the UI (categories, formats, doc kinds, tactics…). |
| `GET /summary` | Coverage stats: totals, log sources, runbooks/playbooks, ATT&CK tactic coverage, breakdowns. |
| `GET ?category=&status=&criticality=&tag=&q=` | List sensors (summary shape). |
| `GET /{id}` | Full sensor with log sources and documents. |
| `POST /` · `PUT /{id}` · `DELETE /{id}` | Manage sensors (admin). |
| `POST /{id}/log-sources` · `PUT /log-sources/{id}` · `DELETE /log-sources/{id}` | Manage log sources (admin). |
| `POST /{id}/documents` · `PUT /documents/{id}` · `DELETE /documents/{id}` | Manage documents (admin). |
| `GET /{id}/export/markdown` · `GET /{id}/export/json` | Download the full profile. |
| `GET /publish/targets` | Confluence-enabled connections for this tenant. |
| `GET /publish/{connectionId}/spaces` | Spaces available on a connection. |
| `POST /{id}/publish` | Create/update a Confluence page for the sensor or one document. |

### Publishing to Confluence

`POST /api/sensors/{id}/publish` accepts:

```json
{
  "connection_id": 3,
  "space": "12345",           // Cloud: numeric space id · Data Center: space key
  "parent_page_id": "",       // optional
  "document_id": null          // null = full sensor profile; or a document id
}
```

The rendered Markdown is converted to Confluence storage format (tables
included) and prefixed with an info panel noting the page is managed by SOC
Workbench. Publishing is **idempotent**: the stored `confluence_page_id` (or an
exact title match in the space) is updated in place rather than duplicated. The
returned page id and URL are saved on the sensor/document and surfaced in the UI.

Reuse an existing Jira/Confluence connection from the **Integration Hub**; the
same credentials, encryption and permission model apply. No Confluence-enabled
connection? The publish dialog links you to configure one first.

## Deployment & rollback

- **Upgrade:** the app applies migration `0006_equipment_sensors` automatically
  on start (`python -m app.migrations.runner upgrade` runs it explicitly).
- **Rollback:** `python -m app.migrations.runner downgrade 0006_equipment_sensors`
  drops the three tables. No other module depends on them.
- **Access:** grant the `sensors` module to a role/user under **Access &
  Features**, or schedule the `module.sensors` feature window.
