"""Sensitive-information detection, masking, tokenization, and removal (Module 3).

The tokenization mapping is kept locally (encrypted in SQLite) and is NEVER
sent to an LLM. Callers must show the protected preview before any external
LLM call.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models.core import SensitivePattern, TokenMapping
from ..security import decrypt_secret, encrypt_secret

# --- Built-in detectors ---------------------------------------------------
# Order matters: more specific patterns first so they win overlaps.

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6_RE = re.compile(r"\b(?:[A-Fa-f0-9]{1,4}:){2,7}[A-Fa-f0-9]{0,4}\b")
URL_RE = re.compile(r"\bhttps?://[^\s<>()\"']+", re.IGNORECASE)
DOMAIN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"(?:com|net|org|io|ir|co|gov|edu|mil|info|biz|dev|xyz|ru|cn|de|uk|local)\b"
)
# Iranian mobile (09xxxxxxxxx) and generic long digit sequences.
PHONE_RE = re.compile(r"\b(?:0|\+98)?9\d{9}\b|\b\+?\d[\d\s().-]{7,}\d\b")
HASH_RE = re.compile(r"\b[A-Fa-f0-9]{32}\b|\b[A-Fa-f0-9]{40}\b|\b[A-Fa-f0-9]{64}\b")
# Common API-key / token shapes.
APIKEY_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}|Bearer\s+[A-Za-z0-9._\-]{20,})\b"
)
# Hostnames like server01.internal / dc-01
HOSTNAME_RE = re.compile(
    r"\b(?:[a-zA-Z][a-zA-Z0-9]*-?\d+|[a-zA-Z0-9-]+\.(?:internal|corp|lan|local))\b"
)


@dataclass
class Detection:
    label: str
    value: str
    token_prefix: str


@dataclass
class ProtectionResult:
    text: str
    detections: list[Detection] = field(default_factory=list)
    token_map: dict[str, str] = field(default_factory=dict)  # token -> original
    counts: dict[str, int] = field(default_factory=dict)


def _valid_ipv4(value: str) -> bool:
    try:
        ipaddress.IPv4Address(value)
        return True
    except ValueError:
        return False


# (label, regex, token_prefix, validator)
_BUILTIN = [
    ("API_KEY", APIKEY_RE, "APIKEY", None),
    ("EMAIL", EMAIL_RE, "EMAIL", None),
    ("URL", URL_RE, "URL", None),
    ("IPV4", IPV4_RE, "INTERNAL_IP", _valid_ipv4),
    ("IPV6", IPV6_RE, "IPV6", None),
    ("HASH", HASH_RE, "HASH", None),
    ("PHONE", PHONE_RE, "PHONE", None),
    ("DOMAIN", DOMAIN_RE, "DOMAIN", None),
    ("HOSTNAME", HOSTNAME_RE, "HOSTNAME", None),
]


def detect(text: str, db: Session | None = None) -> list[Detection]:
    """Return unique detections, custom user patterns first."""
    found: dict[str, Detection] = {}

    if db is not None:
        patterns = (
            db.query(SensitivePattern)
            .filter(SensitivePattern.enabled.is_(True))
            .all()
        )
        for p in patterns:
            try:
                rx = re.compile(p.pattern) if p.is_regex else re.compile(
                    re.escape(p.pattern)
                )
            except re.error:
                continue
            for m in rx.finditer(text):
                val = m.group(0)
                if val and val not in found:
                    found[val] = Detection(p.label, val, p.token_prefix or "CUSTOM")

    for label, rx, prefix, validator in _BUILTIN:
        for m in rx.finditer(text):
            val = m.group(0).strip()
            if not val or val in found:
                continue
            if validator and not validator(val):
                continue
            found[val] = Detection(label, val, prefix)

    # Longest values first so nested matches replace cleanly.
    return sorted(found.values(), key=lambda d: len(d.value), reverse=True)


# --- Masking helpers ------------------------------------------------------

def _mask_value(det: Detection) -> str:
    v = det.value
    if det.label == "IPV4":
        parts = v.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.x.{parts[3]}"
    if det.label == "EMAIL" and "@" in v:
        local, _, domain = v.partition("@")
        head = local[0] if local else "*"
        return f"{head}***@{domain}"
    if det.label == "PHONE":
        digits = re.sub(r"\D", "", v)
        if len(digits) >= 7:
            return digits[:4] + "x" * (len(digits) - 7) + digits[-3:]
    if det.label in ("API_KEY", "HASH"):
        return v[:4] + "…" + v[-4:] if len(v) > 8 else "****"
    # Generic middle-mask.
    if len(v) <= 4:
        return "*" * len(v)
    keep = max(1, len(v) // 4)
    return v[:keep] + "*" * (len(v) - 2 * keep) + v[-keep:]


def _next_token(prefix: str, seen: dict[str, int]) -> str:
    seen[prefix] = seen.get(prefix, 0) + 1
    return f"{prefix}_{seen[prefix]:03d}"


def protect(
    text: str,
    mode: str = "mask",
    db: Session | None = None,
    persist_scope: str | None = None,
) -> ProtectionResult:
    """Apply protection. mode in {mask, tokenize, remove}.

    If persist_scope and db are given, tokenization mappings are saved locally
    (encrypted) and reused for consistent tokens across documents.
    """
    detections = detect(text, db)
    result = ProtectionResult(text=text, detections=detections)
    counts: dict[str, int] = {}
    token_counter: dict[str, int] = {}

    # Preload existing tokens for the scope so repeated values stay stable.
    existing: dict[str, str] = {}  # original -> token
    if mode == "tokenize" and db is not None and persist_scope is not None:
        for tm in db.query(TokenMapping).filter(
            TokenMapping.scope == persist_scope
        ):
            orig = decrypt_secret(tm.original_encrypted)
            if orig:
                existing[orig] = tm.token
                # Track counter high-water mark per prefix.
                prefix = tm.token.rsplit("_", 1)[0]
                try:
                    n = int(tm.token.rsplit("_", 1)[1])
                    token_counter[prefix] = max(token_counter.get(prefix, 0), n)
                except (ValueError, IndexError):
                    pass

    out = text
    replacements: dict[str, str] = {}
    for index, det in enumerate(detections):
        counts[det.label] = counts.get(det.label, 0) + 1
        if mode == "remove":
            replacement = ""
        elif mode == "tokenize":
            if det.value in existing:
                replacement = existing[det.value]
            else:
                replacement = _next_token(det.token_prefix, token_counter)
                existing[det.value] = replacement
                result.token_map[replacement] = det.value
                if db is not None and persist_scope is not None:
                    db.add(
                        TokenMapping(
                            token=replacement,
                            original_encrypted=encrypt_secret(det.value),
                            label=det.label,
                            scope=persist_scope,
                        )
                    )
        else:  # mask
            replacement = _mask_value(det)
        # Protect replacements behind a private-use placeholder. Without this,
        # a nested detector (for example DOMAIN inside EMAIL) can mask the
        # already-masked output a second time.
        placeholder = f"\ue000SOCWB_{index:04d}\ue001"
        out = out.replace(det.value, placeholder)
        replacements[placeholder] = replacement

    for placeholder, replacement in replacements.items():
        out = out.replace(placeholder, replacement)

    if mode == "tokenize" and db is not None and persist_scope is not None:
        db.commit()

    result.text = out
    result.counts = counts
    return result


def restore(text: str, db: Session, scope: str = "global") -> str:
    """Restore tokenized values from the local mapping. Local use only."""
    mappings = db.query(TokenMapping).filter(TokenMapping.scope == scope).all()
    # Replace longer tokens first.
    for tm in sorted(mappings, key=lambda m: len(m.token), reverse=True):
        original = decrypt_secret(tm.original_encrypted)
        if original:
            text = text.replace(tm.token, original)
    return text
