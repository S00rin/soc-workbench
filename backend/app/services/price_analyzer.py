"""Project price analyzer (Module 17).

Pipeline: extract contract text (reuses services.extract) -> split into
scope-of-work sections with the LLM, or a deterministic heading/paragraph
heuristic when no LLM is configured -> user edits each section's estimated
person-hours and role -> cost is computed from user-supplied coefficients
(hourly rates per role, overhead/contingency/tax/discount percentages) ->
a 3-level WBS (Project > Phase > Task) and a sequential Gantt schedule are
generated from the sections -> a starter RACI matrix is suggested for the
user to edit -> everything exports to Excel and PDF.

Farsi contracts: text extraction is script-agnostic (Unicode in, Unicode
out). PDF export reshapes and bidi-reorders Farsi text for correct glyph
joining/direction, and looks for a Persian-capable system font (e.g.
Noto Naskh/Sans Arabic, Vazirmatn) to embed; if none is installed on the
host, the PDF still lays out correctly but falls back to Helvetica for
those glyphs, and says so in the export footer rather than failing silently.
"""
from __future__ import annotations

import glob
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from ..logging_config import get_logger
from . import llm as llm_service

logger = get_logger(__name__)

CATEGORIES = [
    "initiation", "requirements", "design", "development", "testing",
    "deployment", "training", "project_management", "support", "other",
]

PHASE_ORDER = CATEGORIES

PHASE_LABELS = {
    "en": {
        "initiation": "Initiation", "requirements": "Requirements & Analysis",
        "design": "Design", "development": "Development",
        "testing": "Testing & QA", "deployment": "Deployment",
        "training": "Training & Handover", "project_management": "Project Management",
        "support": "Support & Maintenance", "other": "Other",
    },
    "fa": {
        "initiation": "شروع پروژه", "requirements": "تحلیل نیازمندی‌ها",
        "design": "طراحی", "development": "توسعه", "testing": "تست و کیفیت",
        "deployment": "استقرار", "training": "آموزش و تحویل",
        "project_management": "مدیریت پروژه", "support": "پشتیبانی و نگهداری",
        "other": "سایر",
    },
}


class AnalysisError(Exception):
    pass


# --- Section splitting ------------------------------------------------------

def _roles_from_coefficients(coefficients: dict) -> list[str]:
    rates = (coefficients or {}).get("rates") or {}
    return list(rates.keys()) or ["unassigned"]


def _extract_json_array(text: str) -> list:
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise AnalysisError("The model did not return a JSON array of sections.")
    return json.loads(text[start:end + 1])


SPLIT_SYSTEM_PROMPT_EN = (
    "You are a senior project manager and cost estimator analyzing a client contract "
    "or statement of work (the document may be in Persian/Farsi or English). Read the "
    "WHOLE document and extract the scope of work: the concrete deliverables and "
    "technical obligations the contractor/vendor must perform. Persian contracts often "
    "express these as numbered clauses (ماده, تبصره, بند, فصل) or under headings like "
    "'موضوع قرارداد', 'شرح خدمات', 'تعهدات مجری/پیمانکار'; treat each distinct "
    "deliverable or technical obligation as one section. MERGE or DROP purely legal or "
    "administrative clauses (parties, payment terms, termination, confidentiality, "
    "dispute resolution, force majeure) — do not bill effort for those. For EACH scope "
    "section return a JSON object with keys: title (short, in the document's language), "
    "category (one of: {categories}), role (one of: {roles}), excerpt (<=280 chars "
    "quoting or summarizing the obligation), estimated_hours (a realistic integer of "
    "person-hours to deliver it). Return ONLY a JSON array of these objects, no prose, "
    "no markdown fences. Base every section on the text; do not invent scope."
)
SPLIT_SYSTEM_PROMPT_FA = (
    "شما یک مدیر پروژه ارشد و کارشناس برآورد هزینه هستید که یک قرارداد یا شرح خدمات مشتری "
    "(به زبان فارسی یا انگلیسی) را تحلیل می‌کنید. کل سند را بخوانید و «دامنه کار» را استخراج "
    "کنید؛ یعنی تحویل‌شدنی‌ها و تعهدات فنی مشخصی که مجری/پیمانکار باید انجام دهد. قراردادهای "
    "فارسی معمولاً این موارد را در قالب ماده، تبصره، بند و فصل، یا زیر عنوان‌هایی مانند «موضوع "
    "قرارداد»، «شرح خدمات» و «تعهدات مجری/پیمانکار» بیان می‌کنند؛ هر تحویل‌شدنی یا تعهد فنی "
    "مجزا را یک بخش در نظر بگیرید. بندهای صرفاً حقوقی یا اداری (طرفین، شرایط و نحوه پرداخت، "
    "فسخ، محرمانگی، حل اختلاف، فورس‌ماژور) را ادغام یا حذف کنید و برایشان تلاش و هزینه در نظر "
    "نگیرید. برای هر بخشِ دامنه کار یک شیء JSON با کلیدهای title (کوتاه، به زبان سند)، "
    "category (یکی از: {categories})، role (یکی از: {roles})، excerpt (حداکثر ۲۸۰ کاراکتر "
    "نقل‌قول یا خلاصه تعهد) و estimated_hours (عدد صحیح واقع‌بینانه نفر-ساعت) برگردانید. فقط یک "
    "آرایه JSON از این اشیاء را بدون هیچ توضیح یا نشانه مارک‌داون برگردانید. هر بخش را بر پایه "
    "متن بسازید؛ دامنه‌ای که در متن نیست اختراع نکنید."
)


def split_sections_with_llm(text: str, language: str, coefficients: dict, cfg) -> list[dict]:
    roles = _roles_from_coefficients(coefficients)
    system = (SPLIT_SYSTEM_PROMPT_FA if language == "fa" else SPLIT_SYSTEM_PROMPT_EN).format(
        categories=", ".join(CATEGORIES), roles=", ".join(roles),
    )
    result = llm_service.complete(system, text[:60000], cfg)
    try:
        raw_sections = _extract_json_array(result.text)
    except (json.JSONDecodeError, AnalysisError) as e:
        raise AnalysisError(f"Could not parse the model's section list: {e}") from e

    sections = []
    for i, item in enumerate(raw_sections):
        if not isinstance(item, dict) or not str(item.get("title") or "").strip():
            continue
        title = str(item["title"]).strip()
        excerpt = str(item.get("excerpt") or "").strip()
        # Trust the model's labels, but repair anything missing or out of range
        # with the same keyword inference the offline path uses.
        category = str(item.get("category") or "").strip().lower()
        if category not in CATEGORIES:
            category = _categorize(title, excerpt)
        role = str(item.get("role") or "").strip().lower()
        if role not in roles:
            role = _infer_role(title, excerpt, roles)
        try:
            hours = float(item.get("estimated_hours") or 0)
        except (TypeError, ValueError):
            hours = 0.0
        sections.append({
            "order_index": i,
            "title": title[:300],
            "category": category,
            "role": role,
            "excerpt": excerpt[:280],
            "estimated_hours": max(0.0, round(hours, 1)),
        })
    if not sections:
        raise AnalysisError("The model returned no usable sections.")
    return sections


# --- Offline (no-LLM) contract structure analysis ---------------------------
#
# The heuristic path has to stand in for a model, so it does real work: it
# understands Persian contract structure (ماده/تبصره/بند/فصل and numbered
# clauses), classifies each section into a delivery category and a discipline
# from bilingual keyword tables, and down-weights purely legal/administrative
# clauses to zero effort. It is still a first draft to edit, not a final quote.

_ZWNJ = "‌"


def _norm(text: str) -> str:
    """Fold Persian text so substring keyword matching is robust: drop the
    zero-width non-joiner, unify Arabic yeh/kaf with their Persian forms, lower
    case, and collapse whitespace."""
    text = (text or "").replace(_ZWNJ, " ").replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"\s+", " ", text).strip().lower()


# Keyword tables are written in the normalized form (spaces instead of ZWNJ).
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "requirements": [
        "requirement", "analysis", "specification", "scope of work", "discovery",
        "نیازمندی", "نیازسنجی", "نیاز سنجی", "تحلیل", "امکان سنجی", "شرح خدمات",
        "مشخصات فنی", "برداشت اطلاعات", "شناخت", "مطالعه",
    ],
    "design": [
        "design", "architecture", "wireframe", "prototype", "mockup", "ui", "ux",
        "طراحی", "معماری", "رابط کاربری", "تجربه کاربری", "نمونه اولیه", "دیزاین",
    ],
    "development": [
        "develop", "implement", "implementation", "build", "coding", "programming",
        "backend", "frontend", "database", "integration", "module",
        "توسعه", "پیاده سازی", "برنامه نویسی", "کدنویسی", "ساخت", "بک اند", "فرانت اند",
        "پایگاه داده", "وب سرویس", "یکپارچه سازی", "ماژول", "سامانه",
    ],
    "testing": [
        "test", "qa", "quality assurance", "verification", "validation", "uat",
        "تست", "آزمون", "آزمایش", "کنترل کیفیت", "تضمین کیفیت", "صحت سنجی", "اعتبارسنجی",
    ],
    "deployment": [
        "deploy", "release", "installation", "go live", "rollout", "launch",
        "استقرار", "نصب", "راه اندازی", "انتشار", "بهره برداری", "عملیاتی",
    ],
    "training": [
        "training", "handover", "documentation", "manual", "knowledge transfer",
        "آموزش", "تحویل", "مستندسازی", "مستند سازی", "راهنما", "مستندات", "انتقال دانش",
    ],
    "project_management": [
        "project management", "planning", "coordination", "kickoff", "reporting",
        "governance", "milestone", "زمان بندی",
        "مدیریت پروژه", "برنامه ریزی", "هماهنگی", "راهبری", "گزارش دهی", "کنترل پروژه", "نظارت",
    ],
    "support": [
        "support", "maintenance", "warranty", "sla", "helpdesk",
        "پشتیبانی", "نگهداری", "نگه داری", "گارانتی", "ضمانت", "خدمات پس از فروش",
    ],
    "initiation": [
        "initiation", "objective", "preliminary", "feasibility", "kickoff",
        "کلیات", "موضوع قرارداد", "اهداف", "شروع پروژه", "آغاز", "پیش نیاز",
    ],
}

ROLE_KEYWORDS: dict[str, list[str]] = {
    "developer": [
        "develop", "implement", "coding", "programming", "backend", "frontend",
        "database", "توسعه", "پیاده سازی", "برنامه نویسی", "کدنویسی", "بک اند", "فرانت اند", "سامانه",
    ],
    "designer": [
        "design", "ui", "ux", "graphic", "wireframe", "prototype",
        "طراحی", "رابط کاربری", "تجربه کاربری", "گرافیک", "دیزاین",
    ],
    "qa_engineer": [
        "test", "qa", "quality", "verification", "uat",
        "تست", "آزمون", "کیفیت", "آزمایش", "اعتبارسنجی",
    ],
    "business_analyst": [
        "requirement", "analysis", "specification", "discovery", "feasibility",
        "نیازمندی", "تحلیل", "امکان سنجی", "شرح خدمات", "نیازسنجی", "نیاز سنجی",
    ],
    "devops_engineer": [
        "deploy", "infrastructure", "server", "installation", "devops",
        "استقرار", "زیرساخت", "سرور", "نصب", "راه اندازی", "دواپس",
    ],
    "security_engineer": [
        "security", "penetration", "pentest", "audit", "hardening", "vulnerability",
        "امنیت", "نفوذ", "ممیزی", "آسیب پذیری", "تست نفوذ",
    ],
    "project_manager": [
        "management", "planning", "coordination", "reporting", "governance",
        "مدیریت", "برنامه ریزی", "هماهنگی", "راهبری", "کنترل پروژه", "زمان بندی",
    ],
}

# Titles that signal a legal/administrative clause rather than billable scope.
# Note "تعهدات کارفرما" (the CLIENT's duties) is boilerplate, while
# "تعهدات مجری/پیمانکار" (the VENDOR's duties) is real scope and is not listed.
_BOILERPLATE_KEYWORDS = [
    "confidential", "termination", "governing law", "force majeure", "signature",
    "parties", "payment term", "payment schedule", "penalty", "dispute", "jurisdiction",
    "طرفین قرارداد", "طرفین", "مبلغ قرارداد", "نحوه پرداخت", "شرایط پرداخت", "فسخ",
    "محرمانگی", "حل اختلاف", "فورس ماژور", "قوه قاهره", "قانون حاکم", "امضا", "امضاء",
    "نشانی", "اقامتگاه", "جریمه", "خسارت", "ضمانت نامه", "مدت قرارداد", "داوری", "تعهدات کارفرما",
]

_CATEGORY_WEIGHT = {
    "development": 1.4, "design": 1.1, "testing": 1.0, "requirements": 0.9,
    "deployment": 0.8, "support": 0.8, "project_management": 0.7, "training": 0.6,
    "initiation": 0.5, "other": 0.7,
}


def _score(hay: str, keywords: list[str]) -> int:
    return sum(hay.count(kw) for kw in keywords)


def _haystack(title: str, body: str) -> str:
    # Title counted twice so a section's heading outweighs incidental body words.
    return _norm(f"{title} \n {title} \n {body[:600]}")


def _categorize(title: str, body: str) -> str:
    hay = _haystack(title, body)
    best, best_score = "other", 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = _score(hay, keywords)
        if score > best_score:
            best, best_score = category, score
    return best


def _infer_role(title: str, body: str, roles: list[str]) -> str:
    hay = _haystack(title, body)
    best, best_score = None, 0
    for role, keywords in ROLE_KEYWORDS.items():
        if role not in roles:
            continue
        score = _score(hay, keywords)
        if score > best_score:
            best, best_score = role, score
    return best or roles[0]


def _is_boilerplate(title: str) -> bool:
    hay = _norm(title)
    return any(kw in hay for kw in _BOILERPLATE_KEYWORDS)


def _estimate_hours(word_count: int, category: str) -> float:
    weight = _CATEGORY_WEIGHT.get(category, 0.7)
    hours = (word_count / 30.0) * weight  # ~30 words of scoped prose per person-hour
    return round(min(240.0, max(4.0, hours)), 1)


def _is_page_marker(title: str) -> bool:
    return bool(re.match(r"^(page|صفحه|slide|sheet)\s*\d", _norm(title)))


# Structure patterns, tried in order of specificity. Each yields (title, body).
_MD_HEADING_RE = re.compile(r"^\s*#{1,4}\s+(.+?)\s*$", re.MULTILINE)
_FA_CLAUSE_RE = re.compile(
    r"^\s*((?:ماده|تبصره|بند|فصل|بخش|پیوست)\s*[\d۰-۹]+)\s*[:.\-–)]*\s*(.*)$",
    re.MULTILINE,
)
_NUM_HEADING_RE = re.compile(
    r"^\s*([\d۰-۹]+(?:[.\-][\d۰-۹]+)*)\s*[.\-)]\s+(.+?)\s*$", re.MULTILINE
)


def _md_title(m: "re.Match") -> str:
    return (m.group(1) or "").strip()


def _fa_clause_title(m: "re.Match") -> str:
    marker, rest = m.group(1).strip(), (m.group(2) or "").strip()
    return f"{marker} - {rest}" if rest else marker


def _num_title(m: "re.Match") -> str:
    return (m.group(2) or "").strip()


_STRUCTURE_PATTERNS = [
    (_MD_HEADING_RE, _md_title),
    (_FA_CLAUSE_RE, _fa_clause_title),
    (_NUM_HEADING_RE, _num_title),
]


def _boundary_chunks(text: str) -> list[tuple[str, str]]:
    """Slice the document into (title, body) sections. Prefers explicit
    structure (markdown headings, then Persian clause markers, then numbered
    clauses); falls back to blank-line-separated paragraphs."""
    for regex, title_of in _STRUCTURE_PATTERNS:
        matches = [m for m in regex.finditer(text) if not _is_page_marker(title_of(m))]
        if len(matches) >= 2:
            chunks = []
            for i, m in enumerate(matches):
                body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                chunks.append((title_of(m), text[m.end():body_end].strip()))
            return chunks
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return [(p.splitlines()[0].strip()[:90], p) for p in paragraphs]


def split_sections_heuristic(text: str, coefficients: dict, language: str = "fa") -> list[dict]:
    """Offline fallback used when no LLM is configured. Understands Persian and
    English contract structure, classifies each section by keyword and produces
    an editable person-hour estimate. Legal/administrative clauses are kept
    visible but priced at zero effort."""
    roles = _roles_from_coefficients(coefficients)
    fallback_label = "بخش" if language == "fa" else "Section"
    order = 0
    sections = []
    for title, body in _boundary_chunks(text):
        title = (title or "").strip()
        body = (body or "").strip()
        if not title and not body:
            continue
        boilerplate = _is_boilerplate(title)
        category = "other" if boilerplate else _categorize(title, body)
        role = roles[0] if boilerplate else _infer_role(title, body, roles)
        word_count = len(f"{title} {body}".split())
        hours = 0.0 if boilerplate else _estimate_hours(word_count, category)
        sections.append({
            "order_index": order,
            "title": (title or f"{fallback_label} {order + 1}")[:300],
            "category": category,
            "role": role,
            "excerpt": (body or title)[:280],
            "estimated_hours": hours,
        })
        order += 1
        if order >= 80:
            break
    if not sections:
        raise AnalysisError("No sections could be identified in the document text.")
    return sections


# --- Cost calculation --------------------------------------------------------

def _field(obj, key, default=None):
    return getattr(obj, key) if hasattr(obj, key) else obj.get(key, default)


def compute_costs(sections: list, coefficients: dict) -> dict:
    coefficients = coefficients or {}
    rates: dict = coefficients.get("rates") or {}
    default_rate = rates.get("unassigned", 35.0)
    overhead = float(coefficients.get("overhead_percent") or 0) / 100.0
    contingency = float(coefficients.get("contingency_percent") or 0) / 100.0
    tax = float(coefficients.get("tax_percent") or 0) / 100.0
    discount = float(coefficients.get("discount_percent") or 0) / 100.0
    currency = coefficients.get("currency") or "USD"

    rows = []
    subtotal = 0.0
    total_hours = 0.0
    for s in sections:
        hours = float(_field(s, "adjusted_hours", 0) or 0)
        role = _field(s, "role", "unassigned") or "unassigned"
        override = _field(s, "hourly_rate_override", None)
        rate = float(override) if override else float(rates.get(role, default_rate))
        line_cost = hours * rate
        subtotal += line_cost
        total_hours += hours
        rows.append({
            "section_id": _field(s, "id"),
            "title": _field(s, "title"),
            "category": _field(s, "category"),
            "role": role,
            "hours": round(hours, 2),
            "rate": round(rate, 2),
            "cost": round(line_cost, 2),
        })

    overhead_amount = subtotal * overhead
    contingency_amount = (subtotal + overhead_amount) * contingency
    pre_discount = subtotal + overhead_amount + contingency_amount
    discount_amount = pre_discount * discount
    taxable = pre_discount - discount_amount
    tax_amount = taxable * tax
    total = taxable + tax_amount

    return {
        "currency": currency,
        "rows": rows,
        "total_hours": round(total_hours, 2),
        "subtotal": round(subtotal, 2),
        "overhead_amount": round(overhead_amount, 2),
        "contingency_amount": round(contingency_amount, 2),
        "discount_amount": round(discount_amount, 2),
        "tax_amount": round(tax_amount, 2),
        "total": round(total, 2),
    }


# --- WBS generation (3 levels: Project > Phase > Task) ----------------------

def generate_wbs(contract_title: str, sections: list, language: str = "en") -> list[dict]:
    """Returns a flat list of dicts (no DB ids yet) in parent-first order:
    one level-1 root, one level-2 node per phase present, one level-3 node
    per contract section. Each dict carries a `_parent_code` used by the
    caller to resolve real parent_id after the root/phases are persisted."""
    labels = PHASE_LABELS.get(language, PHASE_LABELS["en"])
    by_category: dict[str, list] = {}
    for s in sections:
        cat = _field(s, "category", "other") or "other"
        by_category.setdefault(cat, []).append(s)
    ordered_categories = [c for c in PHASE_ORDER if c in by_category]

    root_title = contract_title.strip() if contract_title and contract_title.strip() else ("پروژه" if language == "fa" else "Project")
    items: list[dict] = [{
        "level": 1, "code": "1", "title": root_title, "order_index": 0,
        "section_id": None, "_parent_code": None,
    }]
    for pi, category in enumerate(ordered_categories, 1):
        phase_code = f"1.{pi}"
        items.append({
            "level": 2, "code": phase_code, "title": labels.get(category, category.replace("_", " ").title()),
            "order_index": pi, "section_id": None, "_parent_code": "1",
        })
        for ti, section in enumerate(by_category[category], 1):
            items.append({
                "level": 3, "code": f"{phase_code}.{ti}",
                "title": _field(section, "title"), "order_index": ti,
                "section_id": _field(section, "id"), "_parent_code": phase_code,
            })
    return items


def parse_date(value: str | None) -> date:
    if value:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    return date.today()


def schedule_wbs(wbs_rows: list[dict], hours_by_section: dict[int, float], hours_per_day: float, start: str | None) -> dict[int, dict]:
    """wbs_rows: persisted rows (dicts) with real `id`/`parent_id`. Schedules
    level-3 tasks sequentially (single shared timeline) in code order; level-1
    and level-2 spans are the min/max of their descendants. Returns
    {item_id: {"start": date, "end": date, "duration": float}}."""
    hours_per_day = hours_per_day or 8.0
    start_date = parse_date(start)
    children: dict[int | None, list[dict]] = {}
    for row in wbs_rows:
        children.setdefault(row["parent_id"], []).append(row)
    for lst in children.values():
        lst.sort(key=lambda r: r["order_index"])

    schedule: dict[int, dict] = {}
    cursor = start_date

    def schedule_leaf(row: dict) -> tuple[date, date]:
        nonlocal cursor
        hours = float(hours_by_section.get(row["section_id"], 0) or 0)
        duration = max(1.0, round(hours / hours_per_day, 2)) if hours else 1.0
        s = cursor
        e = s + timedelta(days=max(0, int(round(duration)) - 1))
        schedule[row["id"]] = {"start": s, "end": e, "duration": duration}
        cursor = e + timedelta(days=1)
        return s, e

    def visit(row: dict) -> tuple[date, date]:
        kids = children.get(row["id"], [])
        if not kids:
            if row["level"] == 3:
                return schedule_leaf(row)
            schedule[row["id"]] = {"start": cursor, "end": cursor, "duration": 0.0}
            return cursor, cursor
        starts, ends = [], []
        for kid in kids:
            s, e = visit(kid)
            starts.append(s)
            ends.append(e)
        span_s, span_e = min(starts), max(ends)
        schedule[row["id"]] = {"start": span_s, "end": span_e, "duration": float((span_e - span_s).days + 1)}
        return span_s, span_e

    for root in children.get(None, []):
        visit(root)
    return schedule


def suggest_raci(wbs_rows: list[dict], manager_label: str = "Project Manager", owner_label: str = "Section Owner") -> list[dict]:
    """Starter RACI suggestion for every level-3 task: the PM is Accountable,
    a placeholder Section Owner is Responsible. Fully editable afterwards."""
    entries = []
    for row in wbs_rows:
        if row["level"] != 3:
            continue
        entries.append({"wbs_item_id": row["id"], "participant": manager_label, "raci": "A"})
        entries.append({"wbs_item_id": row["id"], "participant": owner_label, "raci": "R"})
    return entries


# --- RTL text shaping for PDF export -----------------------------------------

def shape_for_pdf(text: str, language: str) -> str:
    if language != "fa" or not text:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(text))
    except ImportError:
        return text


_RTL_FONT_CANDIDATES = [
    "*Vazirmatn*Regular*.ttf", "*Vazir*.ttf", "*NotoNaskhArabic*Regular*.ttf",
    "*NotoNaskhArabic*.ttf", "*NotoSansArabic*Regular*.ttf", "*NotoSansArabic*.ttf", "*Amiri*Regular*.ttf",
]
_RTL_FONT_DIRS = ["/usr/share/fonts", "/usr/local/share/fonts", str(Path.home() / ".fonts"), str(Path.home() / ".local/share/fonts")]

_rtl_font_name_cache: str | None = None
_rtl_font_resolved = False


def _register_rtl_font() -> str | None:
    """Best-effort: register a Persian-capable TTF found on the host so Farsi
    PDF exports render real glyphs instead of tofu boxes. Returns the
    registered font name, or None if no such font is installed (the export
    still succeeds; Farsi text is shaped/reordered but drawn in Helvetica)."""
    global _rtl_font_name_cache, _rtl_font_resolved
    if _rtl_font_resolved:
        return _rtl_font_name_cache
    _rtl_font_resolved = True
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for base in _RTL_FONT_DIRS:
        for pattern in _RTL_FONT_CANDIDATES:
            for path in glob.glob(f"{base}/**/{pattern}", recursive=True):
                try:
                    pdfmetrics.registerFont(TTFont("PriceAnalyzerRTL", path))
                    _rtl_font_name_cache = "PriceAnalyzerRTL"
                    logger.info("Registered Persian-capable PDF font from %s", path)
                    return _rtl_font_name_cache
                except Exception:  # noqa: BLE001
                    continue
    logger.warning("No Persian-capable font found for PDF export; Farsi glyphs may not render.")
    return None


# --- Excel export -------------------------------------------------------------

def export_excel(contract, cost: dict, wbs_rows: list[dict], raci_entries: list[dict], out_dir: Path, name: str) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    header_fill = PatternFill("solid", fgColor="1A1A2E")
    header_font = Font(color="FFFFFF", bold=True)

    def style_header(ws) -> None:
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font

    def autosize(ws) -> None:
        for col in ws.columns:
            length = max((len(str(c.value)) for c in col if c.value is not None), default=8)
            ws.column_dimensions[get_column_letter(col[0].column)].width = min(60, max(10, length + 2))

    ws = wb.active
    ws.title = "Summary"
    for label, value in [
        ("Contract", contract.title), ("Customer", contract.customer),
        ("Currency", cost["currency"]), ("Total person-hours", cost["total_hours"]),
        ("Subtotal", cost["subtotal"]), ("Overhead", cost["overhead_amount"]),
        ("Contingency", cost["contingency_amount"]), ("Discount", -cost["discount_amount"]),
        ("Tax", cost["tax_amount"]), ("Total", cost["total"]),
    ]:
        ws.append([label, value])
    autosize(ws)

    ws2 = wb.create_sheet("Sections & Cost")
    ws2.append(["#", "Title", "Category", "Role", "Hours", "Rate", "Cost"])
    style_header(ws2)
    for i, row in enumerate(cost["rows"], 1):
        ws2.append([i, row["title"], row["category"], row["role"], row["hours"], row["rate"], row["cost"]])
    autosize(ws2)

    ws3 = wb.create_sheet("WBS & Gantt")
    ws3.append(["Code", "Level", "Title", "Start", "End", "Duration (d)", "% Complete", "Assignee"])
    style_header(ws3)
    for row in wbs_rows:
        ws3.append([row["code"], row["level"], row["title"], row["start_date"], row["end_date"],
                    row["duration_days"], row["percent_complete"], row["assignee"]])
    autosize(ws3)

    ws4 = wb.create_sheet("RACI")
    participants = sorted({e["participant"] for e in raci_entries}) or ["Participant"]
    ws4.append(["WBS Item"] + participants)
    style_header(ws4)
    titles = {row["id"]: f'{row["code"]} {row["title"]}' for row in wbs_rows}
    by_item: dict[int, dict[str, str]] = {}
    for e in raci_entries:
        by_item.setdefault(e["wbs_item_id"], {})[e["participant"]] = e["raci"]
    for item_id, values in by_item.items():
        ws4.append([titles.get(item_id, str(item_id))] + [values.get(p, "") for p in participants])
    autosize(ws4)

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.xlsx"
    wb.save(str(path))
    return path


# --- PDF export ----------------------------------------------------------------

def export_pdf(contract, cost: dict, wbs_rows: list[dict], raci_entries: list[dict], out_dir: Path, name: str) -> Path:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

    language = contract.language or "en"
    font_name = _register_rtl_font() if language == "fa" else None
    base_font = font_name or "Helvetica"
    bold_font = font_name or "Helvetica-Bold"

    def t(text: object) -> str:
        return shape_for_pdf(str(text if text is not None else ""), language)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("PATitle", parent=styles["Title"], fontName=bold_font,
                                  alignment=2 if language == "fa" else 0)
    heading_style = ParagraphStyle("PAHeading", parent=styles["Heading2"], fontName=bold_font,
                                    alignment=2 if language == "fa" else 0)
    body_style = ParagraphStyle("PABody", parent=styles["Normal"], fontName=base_font,
                                 alignment=2 if language == "fa" else 0)

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4),
                             leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    story: list = []

    story.append(Paragraph(t(contract.title or "Contract"), title_style))
    subtitle = f"{contract.customer} · {cost['currency']} · generated {datetime.now():%Y-%m-%d %H:%M}"
    story.append(Paragraph(t(subtitle), body_style))
    story.append(Spacer(1, 10))

    story.append(Paragraph(t("Cost summary" if language != "fa" else "خلاصه هزینه"), heading_style))
    summary_rows = [
        [t("Item" if language != "fa" else "شرح"), t("Amount" if language != "fa" else "مبلغ")],
        [t("Total person-hours"), f"{cost['total_hours']:g}"],
        [t("Subtotal"), f"{cost['subtotal']:,.2f}"],
        [t("Overhead"), f"{cost['overhead_amount']:,.2f}"],
        [t("Contingency"), f"{cost['contingency_amount']:,.2f}"],
        [t("Discount"), f"-{cost['discount_amount']:,.2f}"],
        [t("Tax"), f"{cost['tax_amount']:,.2f}"],
        [t("Total"), f"{cost['total']:,.2f} {cost['currency']}"],
    ]
    story.append(_styled_table(summary_rows, [220, 160], base_font, bold_font))
    story.append(Spacer(1, 14))

    story.append(Paragraph(t("Sections & cost" if language != "fa" else "بخش‌ها و هزینه"), heading_style))
    section_rows = [[t(h) for h in ["#", "Title", "Category", "Role", "Hours", "Rate", "Cost"]]]
    for i, row in enumerate(cost["rows"], 1):
        section_rows.append([str(i), t(row["title"]), t(row["category"]), t(row["role"]),
                              f"{row['hours']:g}", f"{row['rate']:,.2f}", f"{row['cost']:,.2f}"])
    story.append(_styled_table(section_rows, [24, 220, 90, 90, 50, 60, 70], base_font, bold_font))
    story.append(PageBreak())

    story.append(Paragraph(t("Work breakdown structure" if language != "fa" else "ساختار شکست کار (WBS)"), heading_style))
    wbs_table_rows = [[t(h) for h in ["Code", "Title", "Start", "End", "Days", "%", "Assignee"]]]
    for row in wbs_rows:
        indent = "    " * (row["level"] - 1)
        wbs_table_rows.append([row["code"], t(f"{indent}{row['title']}"), row["start_date"], row["end_date"],
                                f"{row['duration_days']:g}", f"{row['percent_complete']}%", t(row["assignee"])])
    story.append(_styled_table(wbs_table_rows, [50, 260, 70, 70, 45, 40, 100], base_font, bold_font))
    story.append(Spacer(1, 14))

    story.append(Paragraph(t("Gantt chart" if language != "fa" else "نمودار گانت"), heading_style))
    gantt_rows = [
        {"title": row["title"], "level": row["level"], "start": parse_date(row["start_date"]), "end": parse_date(row["end_date"] or row["start_date"])}
        for row in wbs_rows
    ]
    story.append(_build_gantt_flowable(gantt_rows, width=landscape(A4)[0] - 32 * mm, language=language, font_name=base_font))
    story.append(PageBreak())

    story.append(Paragraph(t("RACI matrix" if language != "fa" else "ماتریس RACI"), heading_style))
    participants = sorted({e["participant"] for e in raci_entries}) or []
    titles = {row["id"]: f'{row["code"]} {row["title"]}' for row in wbs_rows}
    by_item: dict[int, dict[str, str]] = {}
    for e in raci_entries:
        by_item.setdefault(e["wbs_item_id"], {})[e["participant"]] = e["raci"]
    raci_table_rows = [[t("WBS item" if language != "fa" else "مورد WBS")] + [t(p) for p in participants]]
    for item_id, values in by_item.items():
        raci_table_rows.append([t(titles.get(item_id, str(item_id)))] + [values.get(p, "") for p in participants])
    col_widths = [220] + [max(40, 400 // max(1, len(participants))) for _ in participants]
    story.append(_styled_table(raci_table_rows, col_widths, base_font, bold_font))

    if language == "fa" and not font_name:
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            "No Persian-capable font (e.g. Vazirmatn, Noto Naskh Arabic) was found on this server, so Farsi "
            "text above may render with missing glyphs. Install one under /usr/share/fonts and re-export.",
            body_style,
        ))

    doc.build(story)
    return path


def _styled_table(rows: list[list[str]], col_widths: list[int], base_font: str, bold_font: str) -> "Table":
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), bold_font),
        ("FONTNAME", (0, 1), (-1, -1), base_font),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f4f8")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


def _build_gantt_flowable(rows: list[dict], width: float, language: str = "en", font_name: str = "Helvetica", row_height: float = 14):
    """Builds a platypus Flowable drawing a real, date-scaled Gantt chart
    (one horizontal bar per WBS item, indented by level) without pulling in
    a charting dependency."""
    from reportlab.lib import colors
    from reportlab.platypus import Flowable

    class _Gantt(Flowable):
        def __init__(self):
            super().__init__()
            dates = [r["start"] for r in rows] + [r["end"] for r in rows]
            self.min_date = min(dates) if dates else date.today()
            self.max_date = max(dates) if dates else date.today()
            self.label_width = width * 0.32
            self.chart_width = width - self.label_width
            span_days = max(1, (self.max_date - self.min_date).days + 1)
            self.day_width = self.chart_width / span_days
            self.height = row_height * max(1, len(rows)) + 16

        def wrap(self, availWidth, availHeight):
            return width, self.height

        def draw(self):
            c = self.canv
            c.setFont(font_name, 6.5)
            level_colors = {1: colors.HexColor("#16213e"), 2: colors.HexColor("#3f5da8"), 3: colors.HexColor("#7aa7ff")}
            y = self.height - 12
            c.setStrokeColor(colors.HexColor("#dddddd"))
            span_days = max(1, (self.max_date - self.min_date).days + 1)
            for offset in range(0, span_days, 7):
                x = self.label_width + offset * self.day_width
                c.line(x, 0, x, self.height)
            for row in rows:
                offset = (row["start"] - self.min_date).days
                duration_days = max(1, (row["end"] - row["start"]).days + 1)
                x = self.label_width + offset * self.day_width
                w = max(2.0, duration_days * self.day_width)
                indent = (row["level"] - 1) * 8
                c.setFillColor(colors.HexColor("#1a1a2e"))
                label = shape_for_pdf((row["title"] or "")[:44], language)
                c.drawString(2 + indent, y - 8, label)
                c.setFillColor(level_colors.get(row["level"], colors.grey))
                c.roundRect(x, y - 10, w, 8, 2, fill=1, stroke=0)
                y -= row_height

    return _Gantt()
