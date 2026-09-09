from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.atlassian import AtlassianConnection, IntegrationHistory
from app.models.automation import IntelSource, IoCObservation
from app.models.content import Document, IntelItem
from app.models.core import Job
from app.models.entities import IoC, Project, Report
from app.models.governance import ExternalConnection, FeaturePolicy, UserAccount, UserActivity
from app.models.sensors import Sensor, SensorDocument, SensorLogSource
from app.security import AuthContext
from app.services import dashboard_metrics
from app.services.access_control import FEATURE_CATALOG
from app.services.access_middleware import module_for_path, specific_features

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
ADMIN = AuthContext("admin", "default", "admin", user_id=1)
ANALYST = AuthContext("analyst", "default", "analyst", user_id=2)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _seed(db: Session) -> None:
    db.add_all([
        Project(name="Bank SOC onboarding", customer="Bank", status="active", health="green", progress=70,
                risks=[{"title": "Log source delay", "severity": "high"}, "Budget freeze"]),
        Project(name="Ransomware IR", customer="Retail", status="active", health="red", progress=20,
                risks=[{"title": "Closed one", "status": "closed"}]),
        Project(name="Archived", status="closed", health="green", progress=100),
    ])
    for offset, severity in enumerate(["high", "critical", "medium", "low"]):
        db.add(IoC(value=f"10.0.0.{offset}", ioc_type="ipv4", severity=severity, source="ThreatFox",
                   created_at=NOW - timedelta(days=offset), updated_at=NOW))
    db.add(IoC(value="evil.example", ioc_type="domain", severity="high", source="URLhaus", false_positive=True,
               expires_at=(NOW - timedelta(days=1)).isoformat(), created_at=NOW - timedelta(days=45), updated_at=NOW))
    db.add(IoC(value="soon.example", ioc_type="domain", severity="medium", source="URLhaus",
               expires_at=(NOW + timedelta(days=5)).isoformat(), created_at=NOW - timedelta(days=2), updated_at=NOW))
    db.flush()
    correlated = db.query(IoC).filter(IoC.value == "10.0.0.0").one()
    db.add_all([
        IoCObservation(ioc_id=correlated.id, source_name="ThreatFox"),
        IoCObservation(ioc_id=correlated.id, source_name="CISA KEV"),
    ])
    db.add_all([
        IntelItem(title="New campaign", source="Feed A", category="Malware", relevance=0.8, created_at=NOW - timedelta(hours=3), updated_at=NOW),
        IntelItem(title="Old news", source="Feed A", category="Vulnerability", relevance=0.4, created_at=NOW - timedelta(days=40), updated_at=NOW),
        IntelSource(name="Feed A", url="https://a.example/rss", enabled=True, interval_minutes=60,
                    last_success_at=(NOW - timedelta(minutes=30)).isoformat()),
        IntelSource(name="Feed B", url="https://b.example/rss", enabled=True, interval_minutes=60,
                    failure_count=3, last_error="timeout", last_success_at=(NOW - timedelta(days=2)).isoformat()),
        Document(title="Evidence", source_type="file", token_estimate=1200, created_at=NOW - timedelta(days=1), updated_at=NOW),
        Report(title="Weekly", report_type="weekly_soc", status="final", created_at=NOW - timedelta(days=2), updated_at=NOW),
        Report(title="Previous", report_type="weekly_soc", status="final", created_at=NOW - timedelta(days=40), updated_at=NOW),
    ])
    for index in range(4):
        db.add(Job(name=f"job-{index}", kind="intelligence", status="completed" if index else "failed", error="boom" if not index else "",
                   started_at=NOW - timedelta(days=1, seconds=90), finished_at=NOW - timedelta(days=1),
                   created_at=NOW - timedelta(days=1), updated_at=NOW))
    db.add_all([
        AtlassianConnection(tenant_id="default", owner_user_id="admin", name="Jira Cloud", products=["jira"],
                            base_url="https://jira.example", enabled=True, last_success_at=NOW - timedelta(hours=1)),
        ExternalConnection(tenant_id="default", owner_user_id="admin", provider="splunk", name="Splunk",
                           base_url="https://splunk.example", enabled=True, last_error_code="auth_failed"),
        ExternalConnection(tenant_id="other", owner_user_id="mallory", provider="wikijs", name="Other tenant",
                           base_url="https://wiki.example", enabled=True, last_success_at=NOW),
        IntegrationHistory(tenant_id="default", owner_user_id="admin", product="jira", operation_type="search",
                           status="success", duration_ms=250, correlation_id="c1", created_at=NOW - timedelta(hours=2), updated_at=NOW),
        IntegrationHistory(tenant_id="default", owner_user_id="admin", product="jira", operation_type="search",
                           status="failed", error_code="timeout", duration_ms=5000, correlation_id="c2",
                           created_at=NOW - timedelta(hours=1), updated_at=NOW),
        UserAccount(tenant_id="default", username="admin", password_hash="x", role="admin", active=True),
        UserAccount(tenant_id="default", username="analyst", password_hash="x", role="analyst", active=True),
        UserAccount(tenant_id="default", username="former", password_hash="x", role="analyst", active=False),
        FeaturePolicy(tenant_id="default", feature_key="module.reports", enabled=True, expires_at=NOW + timedelta(days=10)),
        FeaturePolicy(tenant_id="default", feature_key="module.data", enabled=True),
    ])
    for index in range(10):
        db.add(UserActivity(tenant_id="default", actor_user_id="admin" if index % 2 else "analyst", module_key="data",
                            action="GET /api/iocs", method="GET", path="/api/iocs", status_code=200 if index < 8 else 500,
                            duration_ms=20 + index * 10, correlation_id=f"a{index}",
                            created_at=NOW - timedelta(hours=index), updated_at=NOW))
    sensor = Sensor(tenant_id="default", slug="ngfw", name="Palo Alto NGFW", category="firewall", status="active",
                    mitre_tactics=["Initial Access", "Command and Control", "Exfiltration"])
    inactive = Sensor(tenant_id="default", slug="old", name="Legacy IDS", category="ids", status="deprecated",
                      mitre_tactics=["Discovery"])
    db.add_all([sensor, inactive])
    db.flush()
    db.add_all([
        SensorLogSource(sensor_id=sensor.id, name="Traffic", eps_estimate=1500, retention_days=90, siem_index="fw"),
        SensorLogSource(sensor_id=sensor.id, name="Threat", eps_estimate=200, retention_days=180),
        SensorDocument(sensor_id=sensor.id, kind="runbook", title="Onboard"),
    ])
    db.commit()


def test_executive_summary_scores_and_compares_periods(db):
    _seed(db)
    summary = dashboard_metrics.executive_summary(db, ADMIN, days=30, now=NOW)

    assert summary["kpis"]["active_investigations"] == 2
    assert summary["kpis"]["red_investigations"] == 1
    assert summary["kpis"]["iocs_new"] == {"value": 5, "previous": 1, "delta": 4, "delta_pct": 400.0}
    assert summary["kpis"]["reports_delivered"]["value"] == 1
    assert summary["kpis"]["reports_delivered"]["previous"] == 1
    assert summary["kpis"]["high_severity_iocs_open"] == 2  # false positive excluded
    assert summary["kpis"]["job_success_rate"] == 75.0
    assert summary["kpis"]["integration_readiness"] == 50.0  # other tenant is invisible
    assert summary["kpis"]["sensor_coverage"] == round(3 / 14 * 100, 1)  # deprecated sensor excluded
    assert summary["kpis"]["users"] == {"total": 3, "active": 2, "engaged": 2}

    assert 0 <= summary["posture"]["score"] <= 100
    assert summary["posture"]["grade"] in "ABCDF"
    components = {item["key"]: item for item in summary["posture"]["components"]}
    assert components["portfolio_health"]["score"] == 50
    assert components["governance"]["score"] == 80
    assert components["intel_freshness"]["score"] == 50.0
    assert abs(sum(item["weight"] for item in summary["posture"]["components"]) - 1) < 1e-9

    assert len(summary["trends"]["iocs"]) == 30
    assert summary["trends"]["iocs"][-1]["date"] == "2026-09-09"
    assert sum(point["count"] for point in summary["trends"]["iocs"]) == 5

    risks = summary["risk_register"]
    assert [entry["risk"] for entry in risks] == ["Log source delay", "Budget freeze"]
    assert risks[0]["severity"] == "high"

    titles = [item["title"] for item in summary["attention"]]
    assert any("red health" in title for title in titles)
    assert any("integration connection" in title for title in titles)
    assert any("module.reports" in title for title in titles)
    assert any("intelligence source" in title for title in titles)
    assert summary["attention"][0]["severity"] == "high"
    assert summary["feature_expiry"][0]["days_left"] == 10


def test_executive_summary_handles_an_empty_database(db):
    summary = dashboard_metrics.executive_summary(db, ADMIN, days=7, now=NOW)
    assert summary["kpis"]["active_investigations"] == 0
    assert summary["kpis"]["job_success_rate"] is None
    assert summary["kpis"]["integration_readiness"] is None
    unmeasured = [item["key"] for item in summary["posture"]["components"] if item["score"] is None]
    assert "automation_reliability" in unmeasured and "integration_readiness" in unmeasured
    assert summary["posture"]["score"] > 0  # governance and coverage still measurable
    brief = dashboard_metrics.render_executive_brief(summary)
    assert "No active investigations." in brief


def test_executive_brief_renders_markdown(db):
    _seed(db)
    summary = dashboard_metrics.executive_summary(db, ADMIN, days=30, now=NOW)
    brief = dashboard_metrics.render_executive_brief(summary)
    assert brief.startswith("# SOC Executive Brief")
    assert "| New IoCs | 5 ▲ 4 (+400.0%) vs previous period |" in brief
    assert "## Needs attention" in brief
    assert "Ransomware IR" in brief
    assert "Log source delay" in brief
    assert "## Detection gaps" in brief


def test_technical_summary_breakdowns(db):
    _seed(db)
    summary = dashboard_metrics.technical_summary(db, ADMIN, days=7, now=NOW)

    iocs = summary["iocs"]
    assert iocs["total"] == 6
    assert iocs["by_type"] == {"ipv4": 4, "domain": 2}
    assert iocs["false_positives"] == 1
    assert iocs["expired"] == 1 and iocs["expiring_30d"] == 1
    assert iocs["multi_source"] == 1
    assert iocs["top_sources"][0] == {"name": "ThreatFox", "count": 4}
    assert iocs["new_24h"] == 2  # NOW and the inclusive 24h boundary

    intel = summary["intel"]
    assert intel["items_period"] == 1 and intel["items_24h"] == 1
    assert intel["source_status"]["healthy"] == 1 and intel["source_status"]["failing"] == 1
    assert intel["by_category"] == {"Malware": 1}

    jobs = summary["jobs"]
    assert jobs["success_rate"] == 75.0
    assert jobs["avg_duration_s"] == 90.0
    assert jobs["by_kind"]["intelligence"] == {"completed": 3, "failed": 1}
    assert jobs["recent_failures"][0]["error"] == "boom"
    assert jobs["scheduler"] == []  # scheduler is not started under test

    integrations = summary["integrations"]
    assert integrations["status_counts"] == {"connected": 1, "error": 1}
    assert integrations["history"]["success_rate"] == 50.0
    assert integrations["history"]["top_errors"] == [{"code": "timeout", "count": 1}]

    telemetry = summary["telemetry"]
    assert telemetry["sensors_total"] == 2
    assert telemetry["eps_total"] == 1700
    assert telemetry["retention_avg_days"] == 135
    assert telemetry["without_siem_index"] == [{"sensor": "Palo Alto NGFW", "log_source": "Threat"}]
    assert telemetry["sensors_without_playbook"] == ["Palo Alto NGFW", "Legacy IDS"]
    assert telemetry["sensors_without_runbook"] == ["Legacy IDS"]
    assert telemetry["coverage"]["covered"] == 3
    assert telemetry["eps_by_sensor"][0] == {"sensor": "Palo Alto NGFW", "eps": 1700}

    api = summary["api"]
    assert api["requests"] == 10 and api["errors"] == 2
    assert api["error_rate"] == 20.0
    assert api["status_classes"]["5xx"] == 2
    assert api["by_module"][0]["module"] == "data"
    assert api["active_users"] == 2
    assert len(api["hourly"]) == 168
    assert sum(point["count"] for point in api["hourly"]) == 10

    storage = summary["storage"]
    assert storage["documents_by_source"] == {"file": 1}
    assert storage["token_estimate_total"] == 1200
    assert storage["reports_by_status"] == {"final": 2}


def test_technical_api_analytics_are_scoped_for_non_admins(db):
    _seed(db)
    summary = dashboard_metrics.technical_summary(db, ANALYST, days=7, now=NOW)
    assert summary["api"]["requests"] == 5
    assert summary["api"]["active_users"] == 1


def test_dashboard_views_are_module_and_feature_gated():
    assert module_for_path("/api/dashboard/executive") == "dashboard"
    assert module_for_path("/api/dashboard/technical") == "dashboard"
    assert specific_features("/api/dashboard/executive") == ["dashboard.executive"]
    assert specific_features("/api/dashboard/executive/brief") == ["dashboard.executive"]
    assert specific_features("/api/dashboard/technical") == ["dashboard.technical"]
    assert specific_features("/api/dashboard") == []
    keys = {item["key"] for item in FEATURE_CATALOG}
    assert {"dashboard.executive", "dashboard.technical"} <= keys
