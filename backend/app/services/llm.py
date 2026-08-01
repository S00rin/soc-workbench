"""LLM provider adapter (Module 4 / Module 15).

Default provider: Anthropic. An Sorin-compatible endpoint is also supported.
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


CLI_PROVIDERS = {"sorin_cli", "codex_cli"}


@dataclass
class LLMConfig:
    provider: str  # anthropic | sorin_compatible | sorin_cli | codex_cli
    model: str
    api_key: str
    base_url: str = ""
    max_tokens: int = 4096
    temperature: float = 0.3
    timeout: int = 120
    sorin_cli_path: str = ""  # optional explicit path to the `sorin` binary
    codex_cli_path: str = ""  # optional explicit path to the `codex` binary

    @property
    def has_credentials(self) -> bool:
        """Local CLI agents (Sorin Code / Codex) use their own subscription
        auth, so they need no api_key."""
        return self.provider in CLI_PROVIDERS or bool(self.api_key)


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
        api_key=o.get("llm_api_key") or s.anthropic_api_key or s.compatible_api_key,
        base_url=o.get("llm_base_url") or s.compatible_base_url,
        max_tokens=int(o.get("llm_max_tokens") or s.llm_max_tokens),
        temperature=float(o.get("llm_temperature") or 0.3),
        timeout=int(o.get("llm_timeout") or s.llm_timeout),
        sorin_cli_path=o.get("sorin_cli_path", ""),
        codex_cli_path=o.get("codex_cli_path", ""),
    )


def complete(system: str, user: str, cfg: LLMConfig) -> LLMResult:
    """Run a single completion. Raises LLMError with a clear message on failure."""
    if not cfg.has_credentials:
        raise LLMError(
            "No LLM credentials configured. Set an API key in Settings → LLM, or "
            "select the 'sorin_cli' (Sorin Code) or 'codex_cli' (Sorin Codex) "
            "provider to use a local CLI agent with your existing subscription."
        )
    logger.info("LLM call provider=%s model=%s (~%d input tokens)",
                cfg.provider, cfg.model, estimate_tokens(system + user))
    if cfg.provider == "sorin_cli":
        return _sorin_cli(system, user, cfg)
    if cfg.provider == "codex_cli":
        return _codex_cli(system, user, cfg)
    if cfg.provider == "anthropic":
        return _anthropic(system, user, cfg)
    return _compatible(system, user, cfg)


def _sorin_cli(system: str, user: str, cfg: LLMConfig) -> LLMResult:
    """Run the completion through the local Sorin Code CLI (`sorin -p`).

    Uses the user's existing Sorin Code authentication instead of an API key.
    The prompt is fed on stdin (not argv) so large documents don't hit the
    command-line length limit. Runs in a temp dir with dynamic project-context
    sections disabled so it behaves like a plain completion, not a repo agent.
    """
    import json
    import shutil
    import subprocess
    import tempfile

    exe = cfg.sorin_cli_path.strip() or shutil.which("sorin") or "sorin"
    # Run as a plain completion, not a repo coding-agent: disable all tools, load
    # no MCP servers, and skip the user's setting sources (hooks / SORIN.md /
    # plugins) so nothing local leaks into the analysis.
    cmd = [
        exe, "-p", "--output-format", "json",
        "--strict-mcp-config",
        "--tools", "",
        "--setting-sources", "",  # load no SORIN.md / hooks / user memory
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
            f"Sorin Code CLI not found ('{exe}'). Install Sorin Code, or set "
            "'sorin_cli_path' in Settings → LLM to its full path."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise LLMError(f"Sorin Code CLI timed out after {cfg.timeout}s.") from e

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:500]
        raise LLMError(f"Sorin Code CLI failed (exit {proc.returncode}): {detail}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise LLMError(f"Could not parse Sorin Code output: {proc.stdout[:300]}") from e

    if data.get("is_error"):
        raise LLMError(f"Sorin Code error: {data.get('result') or data.get('subtype')}")

    text = data.get("result", "")
    usage = data.get("usage") or {}
    model_name = model or "sorin-code"
    model_usage = data.get("modelUsage")
    if isinstance(model_usage, dict) and model_usage:
        # Report the model that produced the most output; Sorin Code may also
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


def _build_codex_command(exe: str, model: str) -> list[str]:
    """Non-interactive Codex invocation. `codex exec` runs a single prompt
    (read from stdin) and prints the assistant's final message to stdout,
    authenticated by the user's `codex login` session — no API key needed."""
    cmd = [exe, "exec", "--skip-git-repo-check", "--color", "never"]
    if model:
        cmd += ["--model", model]
    cmd.append("-")  # read the prompt from stdin instead of argv
    return cmd


def _codex_cli(system: str, user: str, cfg: LLMConfig) -> LLMResult:
    """Run the completion through the local Sorin-compatible Codex CLI (`codex exec`).

    Uses the user's existing Sorin/Codex subscription auth instead of an API
    key. The combined prompt is fed on stdin so large documents don't hit the
    command-line length limit, and it runs in a temp dir so it never touches
    the project. Best-effort: requires the `codex` CLI to be installed and
    `codex login` to have been run.
    """
    import shutil
    import subprocess
    import tempfile

    exe = cfg.codex_cli_path.strip() or shutil.which("codex") or "codex"
    model = (cfg.model or "").strip()
    prompt = f"{system.strip()}\n\n{user}" if system.strip() else user
    cmd = _build_codex_command(exe, model)

    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=cfg.timeout,
            cwd=tempfile.gettempdir(),
        )
    except FileNotFoundError as e:
        raise LLMError(
            f"Codex CLI not found ('{exe}'). Install the Codex CLI, run "
            "'codex login', or set 'codex_cli_path' in Settings → LLM to its full path."
        ) from e
    except subprocess.TimeoutExpired as e:
        raise LLMError(f"Codex CLI timed out after {cfg.timeout}s.") from e

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:500]
        raise LLMError(f"Codex CLI failed (exit {proc.returncode}): {detail}")

    text = (proc.stdout or "").strip()
    if not text:
        raise LLMError("Codex CLI returned no output. Ensure you have run 'codex login'.")
    return LLMResult(
        text=text,
        model=model or "codex",
        input_tokens=estimate_tokens(system + user),
        output_tokens=estimate_tokens(text),
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


def _compatible(system: str, user: str, cfg: LLMConfig) -> LLMResult:
    base = cfg.base_url.rstrip("/")
    if not base:
        raise LLMError("No compatible endpoint URL configured in Settings.")
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
