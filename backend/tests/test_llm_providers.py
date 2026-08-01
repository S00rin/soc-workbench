"""Tests for local-CLI LLM providers (Sorin Code / Codex) that need no API key."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import llm


def test_cli_providers_need_no_api_key():
    assert llm.LLMConfig(provider="sorin_cli", model="", api_key="").has_credentials
    assert llm.LLMConfig(provider="codex_cli", model="", api_key="").has_credentials
    # API-based providers still require a key.
    assert not llm.LLMConfig(provider="anthropic", model="", api_key="").has_credentials
    assert llm.LLMConfig(provider="anthropic", model="", api_key="sk-x").has_credentials


def test_codex_command_is_non_interactive_and_reads_stdin():
    cmd = llm._build_codex_command("codex", "gpt-5-codex")
    assert cmd[:2] == ["codex", "exec"]
    assert "--skip-git-repo-check" in cmd
    assert "--model" in cmd and "gpt-5-codex" in cmd
    assert cmd[-1] == "-"  # prompt read from stdin, not argv


def test_codex_command_omits_model_when_blank():
    cmd = llm._build_codex_command("codex", "")
    assert "--model" not in cmd
    assert cmd[-1] == "-"


def test_config_from_settings_carries_both_cli_paths():
    cfg = llm.config_from_settings({
        "llm_provider": "codex_cli",
        "sorin_cli_path": "/opt/sorin",
        "codex_cli_path": "/opt/codex",
    })
    assert cfg.provider == "codex_cli"
    assert cfg.sorin_cli_path == "/opt/sorin"
    assert cfg.codex_cli_path == "/opt/codex"
    assert cfg.has_credentials  # codex_cli needs no key
