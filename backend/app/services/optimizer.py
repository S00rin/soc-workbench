"""Lightweight content optimization for LLM usage (Module 4).

Reduces tokens by removing boilerplate/duplication while keeping useful
sections. Modes: minimal, balanced, detailed, forensic.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_BOILERPLATE_RE = re.compile(
    r"(?im)^\s*(?:unsubscribe|all rights reserved|confidential(?:ity)? notice|"
    r"this email.*intended|privacy policy|terms of service|cookie policy|"
    r"follow us|sent from my|©|copyright \d{4}).*$"
)
_MENU_RE = re.compile(r"(?im)^\s*(?:home|about|contact|login|sign in|menu)\s*$")


@dataclass
class OptimizationResult:
    text: str
    original_tokens: int
    optimized_tokens: int
    removed_lines: int
    mode: str


def estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 chars/token, adjusted for whitespace-light text."""
    if not text:
        return 0
    return max(1, round(len(text) / 4))


def _dedupe_paragraphs(text: str) -> tuple[str, int]:
    paras = re.split(r"\n\s*\n", text)
    seen: set[str] = set()
    kept: list[str] = []
    removed = 0
    for p in paras:
        key = hashlib.md5(re.sub(r"\s+", " ", p.strip().lower()).encode()).hexdigest()
        if p.strip() and key in seen:
            removed += 1
            continue
        seen.add(key)
        kept.append(p)
    return "\n\n".join(kept), removed


def optimize(text: str, mode: str = "balanced", max_tokens: int | None = None) -> OptimizationResult:
    original_tokens = estimate_tokens(text)
    lines = text.splitlines()
    removed = 0

    cleaned: list[str] = []
    prev_blank = False
    for line in lines:
        stripped = line.strip()
        # Forensic mode preserves almost everything.
        if mode != "forensic":
            if _BOILERPLATE_RE.match(line) or _MENU_RE.match(line):
                removed += 1
                continue
        if not stripped:
            if prev_blank:  # collapse multiple blank lines
                removed += 1
                continue
            prev_blank = True
        else:
            prev_blank = False
        cleaned.append(line.rstrip())

    result = "\n".join(cleaned).strip()

    if mode in ("minimal", "balanced"):
        result, dup = _dedupe_paragraphs(result)
        removed += dup

    if mode == "minimal":
        # Keep only paragraphs that carry signal (headings, lists, longer text).
        keep: list[str] = []
        for para in re.split(r"\n\s*\n", result):
            s = para.strip()
            if s.startswith("#") or s.startswith(("-", "*", "|")) or len(s) > 80:
                keep.append(para)
        result = "\n\n".join(keep) if keep else result

    # Hard cap.
    if max_tokens:
        max_chars = max_tokens * 4
        if len(result) > max_chars:
            result = result[:max_chars].rsplit("\n", 1)[0] + "\n\n_[truncated for token limit]_"

    return OptimizationResult(
        text=result,
        original_tokens=original_tokens,
        optimized_tokens=estimate_tokens(result),
        removed_lines=removed,
        mode=mode,
    )


def chunk(text: str, max_tokens: int = 3000) -> list[str]:
    """Split large text into token-bounded chunks on paragraph boundaries."""
    max_chars = max_tokens * 4
    chunks: list[str] = []
    current = ""
    for para in re.split(r"\n\s*\n", text):
        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(current.strip())
            current = ""
        current += para + "\n\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks


def quick_summary(text: str, max_sentences: int = 3) -> str:
    """Heuristic extractive summary (no LLM). Used as a fallback."""
    sentences = re.split(r"(?<=[.!?؟])\s+", re.sub(r"\s+", " ", text.strip()))
    sentences = [s for s in sentences if len(s) > 30]
    return " ".join(sentences[:max_sentences])
