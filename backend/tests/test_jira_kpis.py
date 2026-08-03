from datetime import datetime, timezone

from app.services.jira_kpis import (
    REPORT_TEMPLATES, calculate_soc_kpis, render_markdown_report, render_template_jql,
)


def issue(*, created, resolution=None, due=None, priority="Medium", assignee=True, status="Open", category="new", ack=None, detected=None):
    return {
        "key": "SOC-1",
        "fields": {
            "created": created,
            "resolutiondate": resolution,
            "duedate": due,
            "priority": {"name": priority},
            "assignee": {"displayName": "Analyst"} if assignee else None,
            "status": {"name": status, "statusCategory": {"key": category}},
            "customfield_ack": ack,
            "customfield_detected": detected,
        },
    }


def test_calculate_common_soc_kpis_and_data_quality():
    rows = [
        issue(
            created="2026-08-01T00:00:00Z", resolution="2026-08-01T12:00:00Z",
            priority="Critical", status="Done", category="done",
            ack="2026-08-01T01:00:00Z", detected="2026-07-31T23:30:00Z",
        ),
        issue(
            created="2026-08-01T00:00:00+00:00", due="2026-08-02",
            priority="High", assignee=False, ack="2026-08-01T02:00:00Z",
            detected="2026-07-31T23:00:00Z",
        ),
    ]
    value = calculate_soc_kpis(
        rows, now=datetime(2026, 8, 3, tzinfo=timezone.utc), sla_target_hours=24,
        acknowledgement_field="customfield_ack", detection_field="customfield_detected",
    )
    metrics = value["metrics"]
    assert metrics["total_issues"]["value"] == 2
    assert metrics["resolved_issues"]["value"] == 1
    assert metrics["open_backlog"]["value"] == 1
    assert metrics["resolution_rate"]["value"] == 50
    assert metrics["mttr"]["value"] == 12
    assert metrics["mtta"]["value"] == 1.5
    assert metrics["mttd"]["value"] == 0.75
    assert metrics["sla_compliance"]["value"] == 100
    assert metrics["unassigned"]["value"] == 1
    assert metrics["overdue"]["value"] == 1
    assert metrics["high_critical"]["value"] == 2
    assert value["data_quality"]["missing"] == []


def test_unavailable_timestamp_kpis_are_explicit_not_guessed():
    value = calculate_soc_kpis([], now=datetime(2026, 8, 3, tzinfo=timezone.utc))
    assert value["metrics"]["mtta"]["value"] is None
    assert value["metrics"]["mttd"]["value"] is None
    assert value["metrics"]["mttr"]["value"] is None
    assert {item["metric"] for item in value["data_quality"]["missing"]} == {"mtta", "mttd", "mttr", "sla_compliance"}


def test_versioned_report_templates_render_safe_jql_and_markdown():
    assert {item["period"] for item in REPORT_TEMPLATES} >= {"daily", "weekly", "monthly"}
    jql = render_template_jql("weekly_soc_performance", "soc")
    assert 'project = "SOC"' in jql
    result = calculate_soc_kpis([], now=datetime(2026, 8, 3, tzinfo=timezone.utc))
    markdown = render_markdown_report(REPORT_TEMPLATES[1], "SOC", result)
    assert "KPI Summary" in markdown
    assert "Suggested analysis prompt" in markdown
    assert "N/A" in markdown
