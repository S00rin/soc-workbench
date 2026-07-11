"""Tests for the credential-free core: detection, masking, tokenization,
optimization, and entity extraction. These are the MVP-critical building blocks."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import entities, optimizer  # noqa: E402
from app.services.sensitive_data import detect, protect  # noqa: E402

SAMPLE = (
    "Contact admin@example.com or call 09121234567. "
    "Server 192.168.10.25 hosts customer.example.com. "
    "See https://intel.example.org/report and CVE-2024-12345. "
    "Company ABC Corp reported the incident."
)


def test_detect_finds_core_types():
    labels = {d.label for d in detect(SAMPLE)}
    assert "EMAIL" in labels
    assert "IPV4" in labels
    assert "URL" in labels
    assert "PHONE" in labels


def test_mask_ipv4_and_email():
    result = protect(SAMPLE, mode="mask")
    assert "192.168.x.25" in result.text
    assert "a***@example.com" in result.text
    assert "admin@example.com" not in result.text


def test_tokenize_is_reversible_map():
    result = protect(SAMPLE, mode="tokenize")
    # Original email should be replaced by a token, mapping retained.
    assert "admin@example.com" not in result.text
    assert any(tok.startswith("EMAIL_") for tok in result.token_map)
    # The map lets local restoration; it must contain originals.
    assert "admin@example.com" in result.token_map.values()


def test_remove_mode_strips_values():
    result = protect(SAMPLE, mode="remove")
    assert "192.168.10.25" not in result.text
    assert "admin@example.com" not in result.text


def test_optimizer_reduces_and_estimates():
    noisy = "Title\n\n" + ("Repeated paragraph.\n\n" * 5) + "Unsubscribe\n"
    out = optimizer.optimize(noisy, mode="balanced")
    assert out.optimized_tokens <= out.original_tokens
    assert out.optimized_tokens > 0


def test_entity_extraction():
    found = entities.extract_all(SAMPLE)
    assert "CVE-2024-12345" in found["cves"]
    assert "192.168.10.25" in found["ips"]
    assert any("example.org" in u for u in found["urls"])


def test_token_estimate_positive():
    assert optimizer.estimate_tokens("hello world") > 0
    assert optimizer.estimate_tokens("") == 0
