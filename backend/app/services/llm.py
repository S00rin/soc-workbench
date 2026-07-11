"""LLM provider adapter (Module 4 / Module 15).

Default provider: Anthropic. An OpenAI-compatible endpoint is also supported.
Secrets come from the Settings store (encrypted) or environment; they are never
logged. Callers are responsible for showing the protected preview BEFORE calling.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..config import get_settings
from ..logging_config import get_logger
from .optimizer import estimate_tokens

logger = get_logger(__name__)


class LLMError(Exception):
    pass


@dataclass
class LLMConfig:
    provider: str  # anthropic | openai | claude_cli
    model: str
    api_key: str
    base_url: str = ""
    max_tokens: int = 4096
    temperature: float = 0.3
    timeout: int = 120
    claude_cli_path: str = ""  # optional explicit path to the `claude` binary

    @property
    def has_credentials(self) -> bool:
        """The local Claude Code CLI uses its own auth, so it needs no api_key."""
        return self.provider == "claude_cli" or bool(self.api_key)


@dataclass
class LLMResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


def config_from_settings(overrides: dict | None = None) -> LLMConfig:
    """Build an LLMConfig from persisted settings + env fallback.

    `overrides` is a plain dict of resolved settings values (already decrypted)
    supplied by the settings service, so this module never touches the DB.
    """
    s = get_settings()
    o = overrides or {}
    provider = o.get("llm_provider") or "anthropic"
    return LLMConfig(
        provider=provider,
        model=o.get("llm_model") or s.default_llm_model,
        api_key=o.get("llm_api_key") or s.anthropic_api_key or s.openai_api_key,
        base_url=o.get("llm_base_url") or s.openai_base_url,
        max_tokens=int(o.get("llm_max_tokens") or s.llm_max_tokens),
        temperature=float(o.get("llm_temperature") or 0.3),
        timeout=int(o.get("llm_timeout") or s.llm_timeout),
        claude_cli_path=o.get("claude_cli_path", ""),
    )


def complete(system: str, user: str, cfg: LLMConfig) -> LLMResult:
    """Run a single completion. Raises LLMError with a clear message on failure."""
    if not cfg.has_credentials:
        raise LLMError(
            "No LLM credentials configured. Set an API key in Settings → LLM, "
            "or select the 'claude_cli' provider to use the local Claude Code agent."
        )
    logger.info("LLM call provider=%s model=%s (~%d input tokens)",
                cfg.provider, cfg.model, estimate_tokens(system + user))
    if cfg.provider == "claude_cli":
        return _claude_cli(system, user, cfg)
    if cfg.provider == "anthropic":
        return _anthropic(system, user, cfg)
    return _openai_compatible(system, user, cfg)


def _claude_cli(system: str, user: str, cfg: LLMConfig) -> LLMResult:
    """Run the completion through the local Claude Code CLI (`claude -p`).

    Uses the user's existing Claude Code authentication instead of an API key.
    The prompt is fed on stdin (not argv) so large documents don't hit the
    command-line length limit. Runs in a temp dir with dynamic project-context
    sections disabled so it behaves like a plain completion, not a repo agent.
    """
    import json
    import shutil
    import subprocess
    import tempfile

    exe = cfg.claude_cli_path.strip() or shutil.which("claude") or "claude"
    # Run as a plain completion, not a repo coding-agent: disable all tools, load
    # no MCP servers, and skip the user's setting sources (hooks / CLAUDE.md /
    # plugins) so nothing local leaks into the analysis.
    cmd = [
        exe, "-p", "--output-format", "json",
        "--strict-mcp-config",
        "--tools", "",
        "--setting-sources", "",  # load no CLAUDE.md / hooks / user memory
    ]
    if system:
        cmd += ["--system-prompt", system, "--exclude-dynamic-system-prompt-sections"]
    model = (cfg.model or "").strip()
    if model:
        cmd += ["--model", model]

    try:
        proc = subprocess.run(
            cmd,
            input=user,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=cfg.timeout,
            cwd=tempfile.gettempdir(),
        )
    except FileNotFoundError as e:
        raise LLMError(
            f"Claude Code CLI not found ('{exe}'). Install Claude Code, or set "
            "'claude_cli_path' in Settings → LLM to its full path."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise LLMError(f"Claude Code CLI timed out after {cfg.timeout}s.") from e

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:500]
        raise LLMError(f"Claude Code CLI failed (exit {proc.returncode}): {detail}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise LLMError(f"Could not parse Claude Code output: {proc.stdout[:300]}") from e

    if data.get("is_error"):
        raise LLMError(f"Claude Code error: {data.get('result') or data.get('subtype')}")

    text = data.get("result", "")
    usage = data.get("usage") or {}
    model_name = model or "claude-code"
    model_usage = data.get("modelUsage")
    if isinstance(model_usage, dict) and model_usage:
        # Report the model that produced the most output; Claude Code may also
        # invoke a small helper model for internal steps.
        model_name = max(
            model_usage,
            key=lambda k: (model_usage[k] or {}).get("outputTokens", 0),
        )
    return LLMResult(
        text=text,
        model=model_name,
        input_tokens=usage.get("input_tokens", estimate_tokens(system + user)),
        output_tokens=usage.get("output_tokens", estimate_tokens(text)),
    )


def _anthropic(system: str, user: str, cfg: LLMConfig) -> LLMResult:
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover
        raise LLMError("anthropic SDK not installed") from e
    client = anthropic.Anthropic(api_key=cfg.api_key, timeout=cfg.timeout)
    try:
        resp = client.messages.create(
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            system=system or "You are a helpful SOC analyst assistant.",
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APIError as e:
        raise LLMError(f"Anthropic API error: {e}") from e
    text = "".join(
        block.text for block in resp.content if getattr(block, "type", "") == "text"
    )
    return LLMResult(
        text=text,
        model=cfg.model,
        input_tokens=getattr(resp.usage, "input_tokens", estimate_tokens(system + user)),
        output_tokens=getattr(resp.usage, "output_tokens", estimate_tokens(text)),
    )


def _openai_compatible(system: str, user: str, cfg: LLMConfig) -> LLMResult:
    base = cfg.base_url.rstrip("/") or "https://api.openai.com/v1"
    url = f"{base}/chat/completions"
    payload = {
        "model": cfg.model,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "messages": [
            {"role": "system", "content": system or "You are a helpful SOC assistant."},
            {"role": "user", "content": user},
        ],
    }
    headers = {"Authorization": f"Bearer {cfg.api_key}"}
    try:
        with httpx.Client(timeout=cfg.timeout) as client:
            r = client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        raise LLMError(f"LLM endpoint error: {e}") from e
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return LLMResult(
        text=text,
        model=cfg.model,
        input_tokens=usage.get("prompt_tokens", estimate_tokens(system + user)),
        output_tokens=usage.get("completion_tokens", estimate_tokens(text)),
    )
