from app.services import attack_lab


def test_catalog_has_all_training_platforms():
    platforms = {item["platform"] for item in attack_lab.list_scenarios()}
    assert {"windows", "linux", "web", "network"} <= platforms


def test_profile_contains_detection_material():
    item = attack_lab.get_scenario("win-powershell-encoded")
    assert item is not None
    assert "index=endpoint" in item["spl"]
    assert item["mitre"][0]["id"] == "T1059.001"
    assert item["log_sources"]
    assert item["triage"]


def test_simulation_is_telemetry_only_and_uses_reserved_addresses():
    run = attack_lab.simulate("network-port-scan")
    assert run is not None
    assert run["mode"] == "telemetry-only"
    assert run["status"] == "completed"
    assert run["event_count"] == len(run["events"])
    assert all(event["lab_generated"] is True for event in run["events"])
    assert run["events"][0]["src_ip"].startswith("192.0.2.")


def test_filter_and_unknown_scenario():
    assert all(item["platform"] == "web" for item in attack_lab.list_scenarios("web"))
    assert attack_lab.list_scenarios(query="T1046")[0]["id"] == "network-port-scan"
    assert attack_lab.get_scenario("missing") is None
    assert attack_lab.simulate("missing") is None
