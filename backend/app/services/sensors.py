"""Equipment & Sensor Library service: rendering, export and seed data."""
from __future__ import annotations

from typing import Iterable

import markdown as _markdown
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models.sensors import Sensor, SensorDocument, SensorLogSource

CATEGORIES = [
    "firewall", "ids_ips", "edr", "antivirus", "waf", "proxy", "dns", "identity",
    "email", "endpoint", "network", "cloud", "siem", "vpn", "nac", "dlp", "other",
]
LOG_FORMATS = ["syslog", "cef", "leef", "json", "windows_event", "api", "csv", "kv", "other"]
COLLECTION_METHODS = ["syslog", "agent", "api", "wef", "file", "netflow", "snmp", "kafka", "other"]
DOC_KINDS = ["overview", "collection", "onboarding", "runbook", "playbook", "reference"]
STATUSES = ["active", "evaluation", "deprecated"]
CRITICALITIES = ["low", "medium", "high", "critical"]
ENVIRONMENTS = ["prod", "staging", "lab", "all"]
MITRE_TACTICS = [
    "Reconnaissance", "Resource Development", "Initial Access", "Execution",
    "Persistence", "Privilege Escalation", "Defense Evasion", "Credential Access",
    "Discovery", "Lateral Movement", "Collection", "Command and Control",
    "Exfiltration", "Impact",
]

DOC_KIND_LABELS = {
    "overview": "Overview", "collection": "Log Collection", "onboarding": "Onboarding",
    "runbook": "Runbook", "playbook": "Playbook", "reference": "Reference",
}


def catalog() -> dict:
    return {
        "categories": CATEGORIES,
        "log_formats": LOG_FORMATS,
        "collection_methods": COLLECTION_METHODS,
        "doc_kinds": DOC_KINDS,
        "doc_kind_labels": DOC_KIND_LABELS,
        "statuses": STATUSES,
        "criticalities": CRITICALITIES,
        "environments": ENVIRONMENTS,
        "mitre_tactics": MITRE_TACTICS,
    }


# --- serialization -------------------------------------------------------

def log_source_out(row: SensorLogSource) -> dict:
    return {
        "id": row.id, "sensor_id": row.sensor_id, "name": row.name, "log_type": row.log_type,
        "format": row.format, "sample": row.sample, "key_fields": row.key_fields or [],
        "siem_sourcetype": row.siem_sourcetype, "siem_index": row.siem_index,
        "mitre_data_source": row.mitre_data_source, "eps_estimate": row.eps_estimate,
        "retention_days": row.retention_days, "order_index": row.order_index,
    }


def document_out(row: SensorDocument) -> dict:
    return {
        "id": row.id, "sensor_id": row.sensor_id, "kind": row.kind, "title": row.title,
        "summary": row.summary, "content": row.content, "severity": row.severity,
        "trigger": row.trigger, "mitre_techniques": row.mitre_techniques or [],
        "tags": row.tags or [], "order_index": row.order_index, "updated_by": row.updated_by,
        "confluence_page_id": row.confluence_page_id, "confluence_url": row.confluence_url,
        "confluence_synced_at": row.confluence_synced_at,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }


def sensor_summary(row: Sensor) -> dict:
    return {
        "id": row.id, "slug": row.slug, "name": row.name, "vendor": row.vendor,
        "product_model": row.product_model, "category": row.category, "status": row.status,
        "criticality": row.criticality, "environment": row.environment, "log_format": row.log_format,
        "collection_methods": row.collection_methods or [], "tags": row.tags or [],
        "mitre_tactics": row.mitre_tactics or [], "owner": row.owner, "is_builtin": row.is_builtin,
        "log_source_count": len(row.log_sources), "document_count": len(row.documents),
        "confluence_page_id": row.confluence_page_id, "confluence_url": row.confluence_url,
        "updated_at": row.updated_at,
    }


def sensor_detail(row: Sensor) -> dict:
    return {
        **sensor_summary(row),
        "description": row.description, "capabilities": row.capabilities or [],
        "deployment_notes": row.deployment_notes, "vendor_url": row.vendor_url, "doc_url": row.doc_url,
        "updated_by": row.updated_by, "confluence_synced_at": row.confluence_synced_at,
        "created_at": row.created_at,
        "log_sources": [log_source_out(item) for item in row.log_sources],
        "documents": [document_out(item) for item in row.documents],
    }


# --- markdown / confluence rendering ------------------------------------

def sensor_to_markdown(row: Sensor) -> str:
    lines: list[str] = [f"# {row.name}", ""]
    meta = [
        ("Vendor", row.vendor), ("Model", row.product_model), ("Category", row.category),
        ("Status", row.status), ("Criticality", row.criticality), ("Environment", row.environment),
        ("Primary log format", row.log_format),
        ("Collection methods", ", ".join(row.collection_methods or [])),
        ("MITRE ATT&CK tactics", ", ".join(row.mitre_tactics or [])),
        ("Owner", row.owner), ("Tags", ", ".join(row.tags or [])),
    ]
    for label, value in meta:
        if value:
            lines.append(f"- **{label}:** {value}")
    lines.append("")
    if row.description:
        lines += ["## Overview", "", row.description, ""]
    if row.capabilities:
        lines += ["## Capabilities", ""]
        for cap in row.capabilities:
            name = cap.get("name", "") if isinstance(cap, dict) else str(cap)
            desc = cap.get("description", "") if isinstance(cap, dict) else ""
            cat = cap.get("category", "") if isinstance(cap, dict) else ""
            suffix = f" — {desc}" if desc else ""
            tag = f" _({cat})_" if cat else ""
            lines.append(f"- **{name}**{tag}{suffix}")
        lines.append("")
    if row.deployment_notes:
        lines += ["## Deployment notes", "", row.deployment_notes, ""]
    if row.log_sources:
        lines += ["## Log sources", "", "| Name | Type | Format | SIEM sourcetype | Index | ~EPS | Retention (d) |",
                  "|---|---|---|---|---|---|---|"]
        for ls in row.log_sources:
            lines.append(
                f"| {ls.name} | {ls.log_type} | {ls.format} | {ls.siem_sourcetype} | "
                f"{ls.siem_index} | {ls.eps_estimate or ''} | {ls.retention_days or ''} |"
            )
        lines.append("")
        for ls in row.log_sources:
            if ls.sample or ls.key_fields or ls.mitre_data_source:
                lines += [f"### {ls.name}", ""]
                if ls.mitre_data_source:
                    lines += [f"- **MITRE data source:** {ls.mitre_data_source}", ""]
                if ls.key_fields:
                    lines += [f"- **Key fields:** {', '.join(ls.key_fields)}", ""]
                if ls.sample:
                    lines += ["```", ls.sample, "```", ""]
    for kind in DOC_KINDS:
        docs = [d for d in row.documents if d.kind == kind]
        if not docs:
            continue
        lines += [f"## {DOC_KIND_LABELS.get(kind, kind.title())}", ""]
        for doc in docs:
            lines += [f"### {doc.title}", ""]
            if doc.severity:
                lines.append(f"- **Severity:** {doc.severity}")
            if doc.trigger:
                lines.append(f"- **Trigger:** {doc.trigger}")
            if doc.mitre_techniques:
                lines.append(f"- **Techniques:** {', '.join(doc.mitre_techniques)}")
            if doc.severity or doc.trigger or doc.mitre_techniques:
                lines.append("")
            if doc.summary:
                lines += [f"*{doc.summary}*", ""]
            if doc.content:
                lines += [doc.content, ""]
    return "\n".join(lines).strip() + "\n"


def document_to_markdown(row: SensorDocument) -> str:
    lines = [f"# {row.title}", ""]
    if row.severity:
        lines.append(f"- **Severity:** {row.severity}")
    if row.trigger:
        lines.append(f"- **Trigger:** {row.trigger}")
    if row.mitre_techniques:
        lines.append(f"- **Techniques:** {', '.join(row.mitre_techniques)}")
    if row.severity or row.trigger or row.mitre_techniques:
        lines.append("")
    if row.summary:
        lines += [f"*{row.summary}*", ""]
    if row.content:
        lines += [row.content, ""]
    return "\n".join(lines).strip() + "\n"


def markdown_to_storage(text: str) -> str:
    """Render markdown to Confluence storage-format XHTML.

    An info panel notes the content is managed by SOC Workbench so manual edits
    in Confluence are not silently overwritten without warning.
    """
    html = _markdown.markdown(text or "", extensions=["extra", "sane_lists", "nl2br"])
    banner = (
        '<ac:structured-macro ac:name="info"><ac:rich-text-body>'
        "<p>This page is published from SOC Workbench. Edits made here may be "
        "overwritten on the next publish.</p>"
        "</ac:rich-text-body></ac:structured-macro>"
    )
    return banner + html


def confluence_title(row: Sensor, document: SensorDocument | None = None) -> str:
    if document is not None:
        label = DOC_KIND_LABELS.get(document.kind, document.kind.title())
        return f"{row.name} — {label}: {document.title}"
    return f"{row.name} — Sensor Profile"


# --- coverage summary ----------------------------------------------------

def coverage_summary(rows: Iterable[Sensor]) -> dict:
    rows = list(rows)
    by_category: dict[str, int] = {}
    by_criticality: dict[str, int] = {}
    by_status: dict[str, int] = {}
    tactics: dict[str, int] = {}
    log_sources = 0
    documents = 0
    playbooks = 0
    runbooks = 0
    for row in rows:
        by_category[row.category] = by_category.get(row.category, 0) + 1
        by_criticality[row.criticality] = by_criticality.get(row.criticality, 0) + 1
        by_status[row.status] = by_status.get(row.status, 0) + 1
        for tactic in row.mitre_tactics or []:
            tactics[tactic] = tactics.get(tactic, 0) + 1
        log_sources += len(row.log_sources)
        documents += len(row.documents)
        playbooks += sum(1 for d in row.documents if d.kind == "playbook")
        runbooks += sum(1 for d in row.documents if d.kind == "runbook")
    return {
        "total_sensors": len(rows),
        "log_sources": log_sources,
        "documents": documents,
        "playbooks": playbooks,
        "runbooks": runbooks,
        "by_category": by_category,
        "by_criticality": by_criticality,
        "by_status": by_status,
        "tactic_coverage": tactics,
        "tactics_covered": len(tactics),
        "tactics_total": len(MITRE_TACTICS),
    }


# --- seed data -----------------------------------------------------------

SEED_SENSORS: list[dict] = [
    {
        "slug": "palo-alto-ngfw",
        "name": "Palo Alto Networks NGFW",
        "vendor": "Palo Alto Networks",
        "product_model": "PA-Series / VM-Series (PAN-OS)",
        "category": "firewall",
        "status": "active",
        "criticality": "critical",
        "environment": "prod",
        "log_format": "csv",
        "collection_methods": ["syslog", "api"],
        "vendor_url": "https://www.paloaltonetworks.com/",
        "mitre_tactics": ["Command and Control", "Exfiltration", "Initial Access", "Discovery"],
        "tags": ["perimeter", "ngfw", "network"],
        "description": (
            "Next-generation firewall providing App-ID, User-ID, Content-ID, threat "
            "prevention, URL filtering and decryption. A primary perimeter and "
            "segmentation control and a high-value telemetry source for the SOC."
        ),
        "capabilities": [
            {"name": "App-ID", "category": "detection", "description": "Application-layer traffic identification independent of port."},
            {"name": "Threat Prevention", "category": "prevention", "description": "IPS, anti-malware and anti-spyware signatures."},
            {"name": "URL Filtering", "category": "prevention", "description": "Category-based web access control and logging."},
            {"name": "WildFire", "category": "detection", "description": "Cloud sandbox verdicts for unknown files."},
            {"name": "SSL Decryption", "category": "logging", "description": "Inbound/outbound decryption for inspection."},
        ],
        "deployment_notes": (
            "Forward logs over syslog to the SIEM using a **Syslog Server Profile** and a "
            "**Log Forwarding Profile** attached to security rules. Prefer the enhanced "
            "application logging and the BSD/IETF format. Send Traffic, Threat, URL, "
            "WildFire and System logs at minimum."
        ),
        "log_sources": [
            {
                "name": "Traffic logs", "log_type": "traffic", "format": "csv",
                "siem_sourcetype": "pan:traffic", "siem_index": "netfw",
                "mitre_data_source": "Network Traffic", "eps_estimate": 5000, "retention_days": 90,
                "key_fields": ["src", "dst", "app", "action", "bytes", "rule"],
                "sample": "1,2024/01/02 10:00:00,001801000000,TRAFFIC,end,2561,2024/01/02 10:00:00,10.0.0.5,203.0.113.9,...,web-browsing,vsys1,trust,untrust,allow",
            },
            {
                "name": "Threat logs", "log_type": "threat", "format": "csv",
                "siem_sourcetype": "pan:threat", "siem_index": "netfw",
                "mitre_data_source": "Application Log", "eps_estimate": 400, "retention_days": 180,
                "key_fields": ["threatid", "severity", "src", "dst", "action", "category"],
                "sample": "1,2024/01/02 10:05:00,001801000000,THREAT,vulnerability,2561,...,critical,client-to-server,reset-both",
            },
            {
                "name": "URL filtering logs", "log_type": "url", "format": "csv",
                "siem_sourcetype": "pan:url", "siem_index": "netproxy",
                "mitre_data_source": "Network Traffic", "eps_estimate": 2000, "retention_days": 90,
                "key_fields": ["url", "category", "action", "src", "user"],
                "sample": "1,2024/01/02 10:06:00,001801000000,THREAT,url,...,malware,block-url,example.test",
            },
        ],
        "documents": [
            {
                "kind": "collection", "title": "Onboard PAN-OS logs to Splunk",
                "summary": "Configure syslog forwarding and validate ingestion.",
                "order_index": 0,
                "content": (
                    "## Prerequisites\n- Splunk HEC or a syslog receiver reachable from the firewall\n"
                    "- Splunk_TA_paloalto_networks installed on indexers/heavy forwarders\n\n"
                    "## Steps\n1. **Device > Server Profiles > Syslog** — add the SIEM collector.\n"
                    "2. **Objects > Log Forwarding** — create a profile forwarding Traffic, "
                    "Threat, URL, WildFire and System logs.\n3. Attach the profile to every "
                    "security policy rule (and set it as the default).\n4. Enable **enhanced "
                    "application logging**.\n5. Verify with `index=netfw sourcetype=pan:traffic` "
                    "within 5 minutes.\n\n## Validation\n- Confirm event counts are non-zero for "
                    "each sourcetype.\n- Check for parsing errors (`punct` anomalies) in the last hour."
                ),
            },
            {
                "kind": "runbook", "title": "Firewall log volume drops to zero",
                "summary": "Restore visibility when a firewall stops sending logs.",
                "order_index": 0,
                "content": (
                    "## Trigger\nNo `pan:traffic` events for a device for > 10 minutes.\n\n"
                    "## Actions\n1. Confirm the device is reachable and not in maintenance.\n"
                    "2. Check **Monitor > Logs > System** for syslog connection errors.\n"
                    "3. Validate the Syslog Server Profile IP/port and TLS settings.\n"
                    "4. Verify the collector is accepting connections (firewall/ACL between "
                    "device and SIEM).\n5. If HA, confirm the active peer is forwarding.\n\n"
                    "## Escalation\nEngage Network Engineering if the device is healthy but "
                    "the collector is unreachable."
                ),
            },
            {
                "kind": "playbook", "title": "Outbound C2 beacon detected at the perimeter",
                "summary": "Contain and investigate suspected command-and-control traffic.",
                "severity": "high", "order_index": 0,
                "trigger": "Threat log C2/spyware signature or repeated allow to a low-reputation destination.",
                "mitre_techniques": ["T1071", "T1571"],
                "content": (
                    "## Triage\n1. Identify source host, user (User-ID) and destination.\n"
                    "2. Pivot on `pan:traffic`/`pan:url` for the source over 24h.\n"
                    "3. Enrich the destination (threat intel, WHOIS, passive DNS).\n\n"
                    "## Containment\n- Block the destination via a security rule or EDL.\n"
                    "- Isolate the host with the EDR if compromise is confirmed.\n\n"
                    "## Eradication & recovery\n- Remove persistence, reset credentials, "
                    "rebuild if warranted.\n\n## Documentation\n- Record IoCs and attach the "
                    "timeline to the incident ticket."
                ),
            },
        ],
    },
    {
        "slug": "windows-security-eventlog",
        "name": "Windows Security Event Log",
        "vendor": "Microsoft",
        "product_model": "Windows Server / Client",
        "category": "endpoint",
        "status": "active",
        "criticality": "critical",
        "environment": "all",
        "log_format": "windows_event",
        "collection_methods": ["wef", "agent"],
        "vendor_url": "https://learn.microsoft.com/windows/security/",
        "mitre_tactics": ["Credential Access", "Privilege Escalation", "Persistence", "Lateral Movement"],
        "tags": ["windows", "authentication", "audit"],
        "description": (
            "The Windows Security channel records authentication, authorization, account "
            "management and audit-policy events. It is the backbone of identity and "
            "endpoint detections. Collect via Windows Event Forwarding (WEF) or a SIEM agent."
        ),
        "capabilities": [
            {"name": "Logon auditing", "category": "logging", "description": "4624/4625/4634 sign-in and failure events."},
            {"name": "Account management", "category": "logging", "description": "User/group creation and modification."},
            {"name": "Process auditing", "category": "detection", "description": "4688 with command line when enabled."},
            {"name": "Kerberos auditing", "category": "detection", "description": "4768/4769/4771 ticket events."},
        ],
        "deployment_notes": (
            "Enable an **advanced audit policy** baseline (logon/logoff, account "
            "management, detailed tracking, object access as needed) via GPO. Enable "
            "**command-line process auditing** (4688). Forward with WEF to a Windows Event "
            "Collector, then ship to the SIEM."
        ),
        "log_sources": [
            {
                "name": "Security channel", "log_type": "authentication", "format": "windows_event",
                "siem_sourcetype": "WinEventLog:Security", "siem_index": "wineventlog",
                "mitre_data_source": "Logon Session", "eps_estimate": 3000, "retention_days": 180,
                "key_fields": ["EventCode", "Account_Name", "Logon_Type", "Source_Network_Address"],
                "sample": "EventCode=4625 An account failed to log on. Logon Type: 3 Account Name: jdoe Source Network Address: 10.0.0.9",
            },
        ],
        "documents": [
            {
                "kind": "collection", "title": "Collect Security logs with WEF",
                "summary": "Forward endpoint security events to the SIEM at scale.",
                "order_index": 0,
                "content": (
                    "## Steps\n1. Stand up a **Windows Event Collector (WEC)** server.\n"
                    "2. Configure a **subscription** for the Security channel with the "
                    "required Event IDs.\n3. Point endpoints at the WEC via GPO "
                    "(`SubscriptionManager`).\n4. Install the SIEM forwarder on the WEC and "
                    "monitor `ForwardedEvents`.\n5. Validate `EventCode=4624` volume per host.\n\n"
                    "## Baseline Event IDs\n4624, 4625, 4634, 4672, 4688, 4720, 4728, 4732, "
                    "4768, 4769, 4771, 4776."
                ),
            },
            {
                "kind": "playbook", "title": "Password-spray / brute-force against a host",
                "summary": "Respond to bursts of failed logons across accounts.",
                "severity": "medium", "order_index": 0,
                "trigger": "Many 4625 events (Logon Type 3) from one source across multiple accounts within a short window.",
                "mitre_techniques": ["T1110", "T1110.003"],
                "content": (
                    "## Triage\n1. Aggregate 4625 by Source Network Address and Account Name.\n"
                    "2. Determine whether any account eventually succeeded (4624).\n\n"
                    "## Containment\n- Block the source IP at the perimeter.\n- Force password "
                    "reset / lock affected accounts.\n\n## Follow-up\n- Enable account lockout "
                    "and MFA where missing; document impacted identities."
                ),
            },
        ],
    },
    {
        "slug": "ms-defender-endpoint",
        "name": "Microsoft Defender for Endpoint",
        "vendor": "Microsoft",
        "product_model": "MDE (Defender XDR)",
        "category": "edr",
        "status": "active",
        "criticality": "high",
        "environment": "prod",
        "log_format": "json",
        "collection_methods": ["api", "agent"],
        "vendor_url": "https://learn.microsoft.com/defender-endpoint/",
        "mitre_tactics": ["Execution", "Persistence", "Defense Evasion", "Discovery", "Lateral Movement"],
        "tags": ["edr", "xdr", "endpoint"],
        "description": (
            "Endpoint detection and response with behavioural detections, alerts, and rich "
            "device/process/network telemetry via advanced hunting tables. Streamed to the "
            "SIEM through the streaming API or connectors."
        ),
        "capabilities": [
            {"name": "Behavioural EDR alerts", "category": "detection", "description": "Correlated detections mapped to MITRE ATT&CK."},
            {"name": "Advanced hunting", "category": "detection", "description": "KQL over Device* telemetry tables."},
            {"name": "Response actions", "category": "prevention", "description": "Isolate device, collect package, restrict app execution."},
            {"name": "Live response", "category": "prevention", "description": "Remote investigation shell."},
        ],
        "deployment_notes": (
            "Onboard devices via the platform-appropriate package. Stream alerts and "
            "advanced-hunting events using the **streaming API** to an event hub / storage, "
            "or use the SIEM's native MDE connector. Ensure the app registration has the "
            "correct API permissions."
        ),
        "log_sources": [
            {
                "name": "Alerts", "log_type": "alert", "format": "json",
                "siem_sourcetype": "mde:alerts", "siem_index": "edr",
                "mitre_data_source": "Application Log", "eps_estimate": 50, "retention_days": 365,
                "key_fields": ["AlertId", "Severity", "Category", "DeviceName", "Techniques"],
                "sample": '{"AlertId":"da637...","Title":"Suspicious PowerShell","Severity":"High","Category":"Execution"}',
            },
            {
                "name": "DeviceProcessEvents", "log_type": "process", "format": "json",
                "siem_sourcetype": "mde:deviceprocessevents", "siem_index": "edr",
                "mitre_data_source": "Process Creation", "eps_estimate": 4000, "retention_days": 30,
                "key_fields": ["DeviceName", "FileName", "ProcessCommandLine", "InitiatingProcessFileName"],
                "sample": '{"DeviceName":"ws01","FileName":"powershell.exe","ProcessCommandLine":"powershell -enc ..."}',
            },
        ],
        "documents": [
            {
                "kind": "collection", "title": "Stream MDE events to the SIEM",
                "summary": "Enable the streaming API and validate ingestion.",
                "order_index": 0,
                "content": (
                    "## Steps\n1. In the Defender portal enable **Streaming API** to an Event "
                    "Hub or storage account.\n2. Select alert and advanced-hunting event types.\n"
                    "3. Configure the SIEM input against the Event Hub / storage.\n"
                    "4. Confirm `mde:alerts` and `mde:deviceprocessevents` are arriving.\n\n"
                    "## Validation\n- Trigger a benign test detection and confirm the alert "
                    "reaches the SIEM end-to-end."
                ),
            },
            {
                "kind": "runbook", "title": "Isolate a compromised device",
                "summary": "Contain an endpoint pending investigation.",
                "order_index": 0,
                "content": (
                    "## Steps\n1. Locate the device in the Defender portal.\n2. Run **Isolate "
                    "device** (full isolation unless comms are required).\n3. Run **Collect "
                    "investigation package**.\n4. Record the action and correlation IDs in the "
                    "ticket.\n5. Release isolation only after eradication is confirmed."
                ),
            },
        ],
    },
    {
        "slug": "zeek-network-sensor",
        "name": "Zeek Network Sensor",
        "vendor": "The Zeek Project",
        "product_model": "Zeek (open source)",
        "category": "network",
        "status": "active",
        "criticality": "high",
        "environment": "prod",
        "log_format": "json",
        "collection_methods": ["file", "kafka"],
        "vendor_url": "https://zeek.org/",
        "mitre_tactics": ["Command and Control", "Discovery", "Lateral Movement", "Exfiltration"],
        "tags": ["nsm", "network", "dns", "http"],
        "description": (
            "A network security monitor that turns raw traffic into high-fidelity, "
            "protocol-aware logs (conn, dns, http, ssl, files, notice). Deployed on a "
            "SPAN/TAP, it is a cornerstone of network detection and hunting."
        ),
        "capabilities": [
            {"name": "Protocol analysis", "category": "detection", "description": "Structured logs for dozens of protocols."},
            {"name": "File extraction", "category": "logging", "description": "Carve and hash files seen on the wire."},
            {"name": "Notice framework", "category": "detection", "description": "Scriptable alerts on observed behaviour."},
            {"name": "Intelligence framework", "category": "detection", "description": "Match traffic against IoC feeds."},
        ],
        "deployment_notes": (
            "Place the sensor on a SPAN port or network TAP with sufficient throughput. "
            "Enable JSON logging and ship logs from `/opt/zeek/logs/current` with the SIEM "
            "forwarder, or publish to Kafka. Prioritise conn, dns, http, ssl, files and notice."
        ),
        "log_sources": [
            {
                "name": "conn.log", "log_type": "connection", "format": "json",
                "siem_sourcetype": "zeek:conn", "siem_index": "zeek",
                "mitre_data_source": "Network Traffic", "eps_estimate": 8000, "retention_days": 60,
                "key_fields": ["id.orig_h", "id.resp_h", "id.resp_p", "proto", "duration", "orig_bytes"],
                "sample": '{"ts":1700000000.0,"id.orig_h":"10.0.0.5","id.resp_h":"203.0.113.9","id.resp_p":443,"proto":"tcp"}',
            },
            {
                "name": "dns.log", "log_type": "dns", "format": "json",
                "siem_sourcetype": "zeek:dns", "siem_index": "zeek",
                "mitre_data_source": "Network Traffic", "eps_estimate": 6000, "retention_days": 60,
                "key_fields": ["query", "qtype_name", "answers", "id.orig_h"],
                "sample": '{"ts":1700000000.0,"query":"example.test","qtype_name":"A","answers":["203.0.113.9"]}',
            },
        ],
        "documents": [
            {
                "kind": "collection", "title": "Ship Zeek JSON logs to the SIEM",
                "summary": "Forward protocol logs from a Zeek sensor.",
                "order_index": 0,
                "content": (
                    "## Steps\n1. Set `redef LogAscii::use_json = T;` (or use the JSON policy).\n"
                    "2. Point the SIEM forwarder at `/opt/zeek/logs/current/*.log` with per-file "
                    "sourcetypes.\n3. Map `zeek:conn`, `zeek:dns`, `zeek:http`, `zeek:ssl`, "
                    "`zeek:files`, `zeek:notice`.\n4. Validate event flow and timestamps.\n\n"
                    "## Tip\nUse Kafka for high-throughput sensors to decouple the SIEM."
                ),
            },
            {
                "kind": "playbook", "title": "DNS tunnelling / exfiltration",
                "summary": "Investigate suspicious DNS behaviour.",
                "severity": "high", "order_index": 0,
                "trigger": "High volume of long/random subdomains or TXT queries from a single host in zeek:dns.",
                "mitre_techniques": ["T1071.004", "T1048"],
                "content": (
                    "## Triage\n1. Aggregate `zeek:dns` by source host and second-level domain.\n"
                    "2. Look for high query counts, long names, unusual record types.\n"
                    "3. Correlate with `zeek:conn` bytes to the resolver.\n\n"
                    "## Containment\n- Sinkhole the domain, block at the resolver/firewall.\n"
                    "- Isolate the source host if data movement is confirmed.\n\n"
                    "## Follow-up\n- Preserve pcap if available; document domains and volumes."
                ),
            },
        ],
    },
]


def seed_default_sensors(db: Session, tenant_id: str | None = None) -> None:
    """Insert built-in reference sensors. Idempotent; never overwrites edits."""
    tenant_id = tenant_id or get_settings().default_tenant_id
    for spec in SEED_SENSORS:
        exists = db.query(Sensor).filter(
            Sensor.tenant_id == tenant_id, Sensor.slug == spec["slug"],
        ).first()
        if exists is not None:
            continue
        fields = {k: v for k, v in spec.items() if k not in {"log_sources", "documents", "owner"}}
        sensor = Sensor(
            tenant_id=tenant_id, is_builtin=True, updated_by="system",
            owner=spec.get("owner", "SOC Engineering"), **fields,
        )
        for index, ls in enumerate(spec.get("log_sources", [])):
            sensor.log_sources.append(SensorLogSource(order_index=index, **{k: v for k, v in ls.items() if k != "order_index"}))
        for index, doc in enumerate(spec.get("documents", [])):
            payload = {k: v for k, v in doc.items() if k != "order_index"}
            payload.setdefault("updated_by", "system")
            sensor.documents.append(SensorDocument(order_index=doc.get("order_index", index), **payload))
        db.add(sensor)
    db.commit()
