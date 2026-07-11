"""Orchestrates the Module 2 workflow: extract -> markdown -> protect ->
optimize -> summarize -> extract entities.

Returns all versions so the UI can display and let the user edit each one.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from sqlalchemy.orm import Session

from . import entities as ent
from . import extract, optimizer
from .sensitive_data import protect


@dataclass
class ProcessedContent:
    title: str
    original_text: str
    markdown: str
    protected_markdown: str
    optimized_markdown: str
    summary: str
    entities: dict = field(default_factory=dict)
    protection_mode: str = "mask"
    optimization_mode: str = "balanced"
    token_estimate: int = 0
    protection_counts: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def process(
    *,
    raw_text: str | None = None,
    file_path: Path | None = None,
    kind: str = "text",
    title: str = "Untitled",
    protection_mode: str = "mask",
    optimization_mode: str = "balanced",
    max_tokens: int | None = None,
    db: Session | None = None,
    token_scope: str | None = None,
) -> ProcessedContent:
    """Run the full processing pipeline for a single input."""
    if file_path is not None:
        markdown = extract.extract_file(file_path)
    elif raw_text is not None:
        markdown = extract.extract_text(raw_text, kind=kind)
    else:
        raise ValueError("Provide either raw_text or file_path")

    original_text = markdown

    # Protect BEFORE optimization so tokens/masks survive cleanup.
    prot = protect(markdown, mode=protection_mode, db=db, persist_scope=token_scope)
    protected_markdown = prot.text

    opt = optimizer.optimize(
        protected_markdown, mode=optimization_mode, max_tokens=max_tokens
    )

    all_entities = ent.extract_all(markdown)  # entities from ORIGINAL (unmasked)
    summary = optimizer.quick_summary(markdown)

    return ProcessedContent(
        title=title,
        original_text=original_text,
        markdown=markdown,
        protected_markdown=protected_markdown,
        optimized_markdown=opt.text,
        summary=summary,
        entities=all_entities,
        protection_mode=protection_mode,
        optimization_mode=optimization_mode,
        token_estimate=opt.optimized_tokens,
        protection_counts=prot.counts,
    )
