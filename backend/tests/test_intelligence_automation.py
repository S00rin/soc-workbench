from app.services.intelligence_automation import _is_due, _normalize_ioc, scope_score


def test_rejects_cloud_only_content():
    score, reason = scope_score("AWS cloud security update", "Kubernetes and API security")
    assert score == 0
    assert reason.startswith("excluded_topic:")


def test_accepts_soc_detection_content():
    score, reason = scope_score(
        "Active ransomware campaign",
        "Threat hunting with Sysmon and Sigma detection engineering rules",
        trust_score=0.9,
    )
    assert score >= 0.55
    assert reason.startswith("matched:")


def test_ioc_normalization_rejects_private_and_placeholder_values():
    assert _normalize_ioc("10.0.0.1", "ipv4") is None
    assert _normalize_ioc("example.com", "domain") is None
    assert _normalize_ioc("8.8.8.8", "ipv4") == "8.8.8.8"
    assert _normalize_ioc("EVIL.Example.NET.", "domain") == "evil.example.net"


def test_source_due_logic():
    assert _is_due("", 60) is True
    assert _is_due("not-a-date", 60) is True
