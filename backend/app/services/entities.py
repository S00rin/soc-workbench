"""Extract entities, keywords, IoCs, and action items from text (Module 2/9)."""
from __future__ import annotations

import re
from collections import Counter

IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
URL_RE = re.compile(r"\bhttps?://[^\s<>()\"']+", re.IGNORECASE)
DOMAIN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9-]+\.)+"
    r"(?:com|net|org|io|ir|co|gov|edu|mil|info|biz|dev|xyz|ru|cn|de|uk)\b"
)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
HASH_RE = re.compile(r"\b[A-Fa-f0-9]{32}\b|\b[A-Fa-f0-9]{40}\b|\b[A-Fa-f0-9]{64}\b")
MITRE_RE = re.compile(r"\bT\d{4}(?:\.\d{3})?\b")
ORG_HINT_RE = re.compile(
    r"\b((?:[A-Z][a-zA-Z0-9&.-]+\s){0,3}?"
    r"(?:Inc|LLC|Ltd|Corp|Corporation|Company|GmbH|Co|Group|Bank|Systems|"
    r"Technologies|Solutions|Security|Networks))\b"
)
ACTION_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:TODO|action item|follow[- ]up|must|should|need to|"
    r"required to|remediate|patch|investigate)\b.*$"
)

_STOPWORDS = set(
    """the a an and or of to in for on with by is are was were be this that
    from as at it its into their our your his her they we you i not no can will
    have has had do does did but if then than so such which who whom whose""".split()
)


def _valid_ip(ip: str) -> bool:
    return all(0 <= int(p) <= 255 for p in ip.split(".")) if ip.count(".") == 3 else False


def extract_iocs(text: str) -> dict[str, list[str]]:
    ips = sorted({m for m in IP_RE.findall(text) if _valid_ip(m)})
    urls = sorted(set(URL_RE.findall(text)))
    # Domains excluding ones already captured inside URLs' hostname noise.
    domains = sorted({d for d in DOMAIN_RE.findall(text)})
    return {
        "ips": ips,
        "urls": urls,
        "domains": domains,
        "emails": sorted(set(EMAIL_RE.findall(text))),
        "hashes": sorted(set(HASH_RE.findall(text))),
        "cves": sorted({c.upper() for c in CVE_RE.findall(text)}),
        "mitre": sorted(set(MITRE_RE.findall(text))),
    }


def extract_keywords(text: str, top: int = 15) -> list[str]:
    words = re.findall(r"[A-Za-z؀-ۿ][A-Za-z0-9؀-ۿ-]{2,}", text)
    counter = Counter(
        w.lower() for w in words if w.lower() not in _STOPWORDS and len(w) > 2
    )
    return [w for w, _ in counter.most_common(top)]


def extract_organizations(text: str, top: int = 10) -> list[str]:
    orgs = {m.strip() for m in ORG_HINT_RE.findall(text)}
    return sorted(orgs)[:top]


def extract_action_items(text: str, top: int = 15) -> list[str]:
    items = [m.strip(" -*").strip() for m in ACTION_RE.findall(text)]
    seen: list[str] = []
    for it in items:
        if it and it not in seen:
            seen.append(it)
    return seen[:top]


def extract_all(text: str) -> dict:
    iocs = extract_iocs(text)
    return {
        **iocs,
        "keywords": extract_keywords(text),
        "organizations": extract_organizations(text),
        "action_items": extract_action_items(text),
    }
