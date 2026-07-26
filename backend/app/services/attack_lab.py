"""Safe, classroom-oriented attack simulation profiles and telemetry.

The lab deliberately models observable attacker behaviour without executing
commands on the host. A future isolated runner can implement the same profile
contract behind an explicit approval boundary.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4


SCENARIOS: list[dict] = [
    {
        "id": "win-powershell-encoded",
        "title": "Suspicious encoded PowerShell",
        "summary": "Model an encoded PowerShell process chain and hunt it with process-creation telemetry.",
        "platform": "windows",
        "difficulty": "beginner",
        "duration_minutes": 20,
        "risk": "medium",
        "mitre": [{"id": "T1059.001", "name": "PowerShell", "tactic": "Execution"}],
        "prerequisites": ["Windows process creation logs", "Sysmon Event ID 1 or Security 4688"],
        "objectives": [
            "Recognize suspicious parent-child process relationships",
            "Separate encoded-command use from ordinary administration",
            "Tune a Splunk analytic using user, host, and parent process",
        ],
        "story": "A user opens a document and a scripting process starts PowerShell with an encoded argument. The lab emits only representative endpoint events; no PowerShell is launched.",
        "simulation_steps": [
            {"title": "Initial process", "detail": "Create a synthetic office-application process event."},
            {"title": "Script execution", "detail": "Emit a child PowerShell event with encoded-command indicators."},
            {"title": "Network follow-up", "detail": "Emit a correlated outbound connection to a reserved documentation address."},
        ],
        "telemetry": ["Microsoft-Windows-Sysmon/Operational", "Windows Security", "EDR process events"],
        "log_sources": [
            {"source": "Sysmon", "event_id": "1", "purpose": "Process creation and command line"},
            {"source": "Sysmon", "event_id": "3", "purpose": "Outbound network connection"},
            {"source": "Security", "event_id": "4688", "purpose": "Fallback process creation"},
        ],
        "spl": (
            "index=endpoint (sourcetype=XmlWinEventLog:Microsoft-Windows-Sysmon/Operational EventCode=1)\n"
            "| eval cmd=lower(CommandLine)\n"
            "| where like(cmd, \"% -enc %\") OR like(cmd, \"%encodedcommand%\")\n"
            "| stats count values(CommandLine) as command_line values(ParentImage) as parent by host user Image\n"
            "| where count >= 1"
        ),
        "triage": [
            "Validate the parent process and interactive user.",
            "Decode the argument in an isolated analysis tool; never execute it.",
            "Correlate process GUID with DNS and network telemetry.",
            "Check whether the host is an approved automation or administration endpoint.",
        ],
        "expected": "The analytic returns the synthetic PowerShell process on win-lab-01 and preserves its parent process for triage.",
        "false_positives": ["Software deployment tools", "Approved administrator scripts", "Endpoint management agents"],
    },
    {
        "id": "linux-cron-persistence",
        "title": "Linux cron persistence",
        "summary": "Simulate modification of a cron definition and correlate file and process evidence.",
        "platform": "linux",
        "difficulty": "intermediate",
        "duration_minutes": 25,
        "risk": "medium",
        "mitre": [{"id": "T1053.003", "name": "Cron", "tactic": "Persistence"}],
        "prerequisites": ["Linux auditd or EDR file telemetry", "Process execution logging"],
        "objectives": [
            "Identify persistence in cron paths",
            "Correlate file writes with the responsible process and user",
            "Tune out approved configuration management",
        ],
        "story": "A compromised service account writes a new cron entry. The simulation creates normalized audit records only and does not change the host filesystem.",
        "simulation_steps": [
            {"title": "Shell activity", "detail": "Emit a synthetic shell process for a service account."},
            {"title": "Cron write", "detail": "Emit an audit file-write record targeting /etc/cron.d."},
            {"title": "Scheduled start", "detail": "Emit a later cron child-process event for correlation."},
        ],
        "telemetry": ["auditd", "Linux EDR", "auth.log"],
        "log_sources": [
            {"source": "auditd", "event_id": "PATH", "purpose": "Write to a monitored cron path"},
            {"source": "auditd", "event_id": "EXECVE", "purpose": "Responsible command and account"},
            {"source": "process", "event_id": "start", "purpose": "Scheduled execution"},
        ],
        "spl": (
            "index=linux (sourcetype=linux:audit path=\"/etc/cron*\" OR file_path=\"/var/spool/cron/*\")\n"
            "| stats count values(process) as process values(cmdline) as command_line by host user file_path\n"
            "| where count >= 1"
        ),
        "triage": [
            "Confirm whether the account normally manages scheduled jobs.",
            "Review package-management and configuration-management change windows.",
            "Inspect the referenced executable safely and collect its hash.",
            "Search for the same file path and account across other Linux hosts.",
        ],
        "expected": "The cron-path write on linux-lab-01 is returned with the service account and responsible shell.",
        "false_positives": ["Ansible or Puppet changes", "Package installation", "Approved backup jobs"],
    },
    {
        "id": "web-sqli-probe",
        "title": "Web SQL injection probe",
        "summary": "Generate benign web-access records resembling SQL injection reconnaissance.",
        "platform": "web",
        "difficulty": "beginner",
        "duration_minutes": 20,
        "risk": "low",
        "mitre": [{"id": "T1190", "name": "Exploit Public-Facing Application", "tactic": "Initial Access"}],
        "prerequisites": ["Reverse-proxy or web-server access logs", "URI and status fields extracted"],
        "objectives": [
            "Detect common SQL metacharacter patterns in normalized URI fields",
            "Use response status and request volume to prioritize",
            "Avoid treating a single signature as proof of exploitation",
        ],
        "story": "A training client sends inert, URL-encoded probe strings to a non-executing lab route. Only synthetic access and WAF records are produced.",
        "simulation_steps": [
            {"title": "Baseline", "detail": "Emit normal requests from a training client."},
            {"title": "Probe burst", "detail": "Emit encoded SQL-like fragments against the lab search route."},
            {"title": "WAF response", "detail": "Emit a correlated block action and HTTP 403 response."},
        ],
        "telemetry": ["Nginx/Apache access", "WAF", "Application gateway"],
        "log_sources": [
            {"source": "web access", "event_id": "request", "purpose": "URI, client, method, and status"},
            {"source": "WAF", "event_id": "942100", "purpose": "SQL injection rule match"},
        ],
        "spl": (
            "index=web (sourcetype=nginx:access OR sourcetype=waf)\n"
            "| eval uri_l=lower(urldecode(uri))\n"
            "| where match(uri_l, \"(?i)(union\\\\s+select|or\\\\s+1=1|information_schema)\")\n"
            "| stats count values(status) as status values(action) as action by src_ip host uri\n"
            "| sort - count"
        ),
        "triage": [
            "Confirm whether the WAF blocked or merely logged the request.",
            "Review application and database errors at the same timestamp.",
            "Compare the client with vulnerability-scanner allowlists.",
            "Search for successful follow-up requests or authentication changes.",
        ],
        "expected": "The probe burst from 192.0.2.44 is grouped, with WAF action and HTTP status visible.",
        "false_positives": ["Authorized vulnerability scanners", "Security tests", "URLs containing user-authored code samples"],
    },
    {
        "id": "network-port-scan",
        "title": "Internal port-scan pattern",
        "summary": "Model one source contacting many destination ports in a short window.",
        "platform": "network",
        "difficulty": "intermediate",
        "duration_minutes": 25,
        "risk": "low",
        "mitre": [{"id": "T1046", "name": "Network Service Discovery", "tactic": "Discovery"}],
        "prerequisites": ["Firewall, Zeek, or NetFlow telemetry", "Normalized source, destination, port, and action"],
        "objectives": [
            "Build a cardinality-based network detection",
            "Distinguish horizontal and vertical scanning",
            "Apply asset role and scanner allowlists during triage",
        ],
        "story": "A training sensor emits connection summaries representing a vertical scan against a reserved lab server. No packets are transmitted.",
        "simulation_steps": [
            {"title": "Connection fan-out", "detail": "Generate connection records across multiple destination ports."},
            {"title": "Firewall outcome", "detail": "Mix allowed and denied synthetic actions."},
            {"title": "Aggregate", "detail": "Demonstrate threshold detection over a five-minute window."},
        ],
        "telemetry": ["Zeek conn.log", "Firewall traffic", "NetFlow"],
        "log_sources": [
            {"source": "Zeek", "event_id": "conn", "purpose": "Connection state and destination port"},
            {"source": "Firewall", "event_id": "traffic", "purpose": "Allow/deny decision"},
        ],
        "spl": (
            "index=network (sourcetype=zeek:conn OR sourcetype=firewall:traffic)\n"
            "| bin _time span=5m\n"
            "| stats dc(dest_port) as unique_ports values(dest_port) as ports count by _time src_ip dest_ip\n"
            "| where unique_ports >= 10\n"
            "| sort - unique_ports"
        ),
        "triage": [
            "Check whether the source is an approved vulnerability scanner.",
            "Identify the source asset owner and logged-on user.",
            "Compare allowed connections with denied attempts.",
            "Look for later authentication or exploitation telemetry.",
        ],
        "expected": "The source 192.0.2.21 crosses the ten-port threshold against 198.51.100.10.",
        "false_positives": ["Vulnerability scanners", "Monitoring systems", "Service inventory tools"],
    },
]


def list_scenarios(platform: str | None = None, query: str | None = None) -> list[dict]:
    """Return compact scenario cards."""
    items = SCENARIOS
    if platform and platform != "all":
        items = [item for item in items if item["platform"] == platform.lower()]
    if query:
        needle = query.lower().strip()
        items = [
            item for item in items
            if needle in f"{item['title']} {item['summary']} {item['platform']} "
            f"{' '.join(t['id'] + ' ' + t['name'] for t in item['mitre'])}".lower()
        ]
    fields = ("id", "title", "summary", "platform", "difficulty", "duration_minutes", "risk", "mitre", "telemetry")
    return [{key: deepcopy(item[key]) for key in fields} for item in items]


def get_scenario(scenario_id: str) -> dict | None:
    return next((deepcopy(item) for item in SCENARIOS if item["id"] == scenario_id), None)


def simulate(scenario_id: str) -> dict | None:
    """Create deterministic representative events without executing an attack."""
    scenario = get_scenario(scenario_id)
    if scenario is None:
        return None
    now = datetime.now(timezone.utc).replace(microsecond=0)
    templates = {
        "win-powershell-encoded": [
            ("process", {"host": "win-lab-01", "user": "student", "EventCode": 1, "Image": "WINWORD.EXE", "ParentImage": "explorer.exe"}),
            ("process", {"host": "win-lab-01", "user": "student", "EventCode": 1, "Image": "powershell.exe", "ParentImage": "WINWORD.EXE", "CommandLine": "powershell.exe -EncodedCommand <LAB_REDACTED>"}),
            ("network", {"host": "win-lab-01", "EventCode": 3, "Image": "powershell.exe", "dest_ip": "198.51.100.25", "dest_port": 443}),
        ],
        "linux-cron-persistence": [
            ("process", {"host": "linux-lab-01", "user": "svc-web", "type": "EXECVE", "process": "sh", "cmdline": "sh <LAB_SIMULATION>"}),
            ("file", {"host": "linux-lab-01", "user": "svc-web", "type": "PATH", "file_path": "/etc/cron.d/lab-maintenance", "action": "created"}),
            ("process", {"host": "linux-lab-01", "user": "svc-web", "type": "EXECVE", "process": "cron", "cmdline": "<LAB_SCHEDULED_ACTION>"}),
        ],
        "web-sqli-probe": [
            ("web", {"host": "web-lab-01", "src_ip": "192.0.2.44", "method": "GET", "uri": "/lab/search?q=baseline", "status": 200}),
            ("web", {"host": "web-lab-01", "src_ip": "192.0.2.44", "method": "GET", "uri": "/lab/search?q=%27+OR+1%3D1--", "status": 403}),
            ("waf", {"host": "web-lab-01", "src_ip": "192.0.2.44", "rule_id": "942100", "action": "blocked", "status": 403}),
        ],
        "network-port-scan": [
            ("network", {"src_ip": "192.0.2.21", "dest_ip": "198.51.100.10", "dest_ports": [21, 22, 23, 25, 53, 80, 110, 135, 139, 443, 445, 3389], "action": "mixed"}),
            ("network", {"src_ip": "192.0.2.21", "dest_ip": "198.51.100.10", "unique_ports": 12, "window": "5m", "result": "threshold_exceeded"}),
        ],
    }
    events = []
    for offset, (kind, fields) in enumerate(templates[scenario_id]):
        events.append({
            "_time": (now + timedelta(seconds=offset * 8)).isoformat(),
            "event_type": kind,
            "lab_generated": True,
            **fields,
        })
    return {
        "run_id": str(uuid4()),
        "scenario_id": scenario_id,
        "status": "completed",
        "mode": "telemetry-only",
        "started_at": now.isoformat(),
        "completed_at": (now + timedelta(seconds=max(1, len(events) - 1) * 8)).isoformat(),
        "events": events,
        "event_count": len(events),
        "safety_notice": "No commands, packets, or filesystem changes were executed. These events are synthetic classroom telemetry.",
    }
