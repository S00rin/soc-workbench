"""Internet intelligence collection (Module 5): RSS feeds + single URLs.

Produces IntelItem-shaped dicts. Persian/English summaries are heuristic by
default and can be upgraded via the LLM in the router.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import feedparser
import httpx

from ..logging_config import get_logger
from . import entities as ent
from . import extract, optimizer

logger = get_logger(__name__)

CATEGORY_HINTS = {
    "Vulnerability": ["cve", "vulnerabilit", "advisory", "patch", "zero-day"],
    "Ransomware": ["ransomware", "ransom", "lockbit", "encryptor"],
    "Malware": ["malware", "trojan", "backdoor", "loader", "stealer"],
    "Threat Intelligence": ["threat actor", "apt", "campaign", "ioc", "ttp"],
    "Splunk": ["splunk", "spl", "search processing"],
    "Detection Engineering": ["detection", "sigma", "yara", "rule"],
    "Incident Response": ["incident", "breach", "forensic", "compromise"],
    "AI": ["llm", "artificial intelligence", "machine learning", "gpt"],
}


@dataclass
class CollectedItem:
    title: str
    original_title: str
    source: str
    url: str
    published_at: str
    content: str
    category: str = "Other"
    tags: list = field(default_factory=list)
    entities: dict = field(default_factory=dict)
    summary_en: str = ""
    summary_fa: str = ""
    original_language: str = "en"
    relevance: float = 0.0
    content_hash: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _hash(url: str, title: str) -> str:
    return hashlib.sha256((url + "|" + title).encode("utf-8")).hexdigest()


def _categorize(text: str) -> str:
    low = text.lower()
    best, score = "Other", 0
    for cat, hints in CATEGORY_HINTS.items():
        c = sum(low.count(h) for h in hints)
        if c > score:
            best, score = cat, c
    return best


def _relevance(entities: dict, text: str) -> float:
    score = 0.0
    score += min(len(entities.get("cves", [])) * 0.15, 0.45)
    score += min(len(entities.get("iocs", []) if isinstance(entities.get("iocs"), list) else []) * 0.05, 0.2)
    score += 0.2 if any(k in text.lower() for k in ("critical", "actively exploited")) else 0
    return round(min(score + 0.3, 1.0), 2)


def _fetch_html(url: str, timeout: int = 20) -> str:
    with httpx.Client(timeout=timeout, follow_redirects=True) as c:
        r = c.get(url, headers={"User-Agent": "SOC-Workbench/1.0"})
        r.raise_for_status()
        return r.text


def collect_url(url: str) -> CollectedItem:
    html = _fetch_html(url)
    md = extract.extract_text(html, kind="html")
    entities = ent.extract_all(md)
    title = md.splitlines()[0].lstrip("# ").strip()[:200] if md else url
    summary = optimizer.quick_summary(md, max_sentences=4)
    return CollectedItem(
        title=title or url,
        original_title=title or url,
        source=url.split("/")[2] if "//" in url else url,
        url=url,
        published_at="",
        content=md,
        category=_categorize(md),
        tags=entities.get("keywords", [])[:6],
        entities=entities,
        summary_en=summary,
        relevance=_relevance(entities, md),
        content_hash=_hash(url, title or url),
    )


def collect_feed(feed_url: str, limit: int = 20) -> list[CollectedItem]:
    parsed = feedparser.parse(feed_url)
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"Could not parse feed: {feed_url}")
    source = parsed.feed.get("title", feed_url)
    items: list[CollectedItem] = []
    for entry in parsed.entries[:limit]:
        title = entry.get("title", "Untitled")
        summary_html = entry.get("summary", "") or entry.get("description", "")
        content = extract.extract_text(summary_html, kind="html") if summary_html else ""
        url = entry.get("link", "")
        entities = ent.extract_all(title + "\n" + content)
        items.append(
            CollectedItem(
                title=title,
                original_title=title,
                source=source,
                url=url,
                published_at=entry.get("published", "") or entry.get("updated", ""),
                content=content,
                category=_categorize(title + " " + content),
                tags=entities.get("keywords", [])[:6],
                entities=entities,
                summary_en=optimizer.quick_summary(content) or title,
                relevance=_relevance(entities, title + " " + content),
                content_hash=_hash(url, title),
            )
        )
    return items
