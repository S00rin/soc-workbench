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
    "You are a senior project manager and cost estimator reviewing a client contract "
    "or statement of work. Split the document into distinct scope-of-work sections "
    "(deliverables, phases or clauses that require effort). For EACH section return "
    "a JSON object with keys: title (short), category (one of: {categories}), "
    "role (one of: {roles}), excerpt (<=280 chars quoting or summarizing the relevant "
    "contract text), estimated_hours (a realistic integer number of person-hours to "
    "deliver that section). Return ONLY a JSON array of these objects, no prose, no "
    "markdown fences. Do not invent scope that is not implied by the text."
)
SPLIT_SYSTEM_PROMPT_FA = (
    "شما یک مدیر پروژه ارشد و کارشناس برآورد هزینه هستید که یک قرارداد یا شرح خدمات "
    "مشتری را بررسی می‌کنید. سند را به بخش‌های مجزای دامنه کار (تحویل‌شدنی‌ها، فازها یا "
    "بندهایی که نیازمند تلاش هستند) تقسیم کنید. برای هر بخش یک شیء JSON با کلیدهای "
    "title (کوتاه)، category (یکی از: {categories})، role (یکی از: {roles})، excerpt "
    "(حداکثر ۲۸۰ کاراکتر نقل‌قول یا خلاصه‌ای از متن قرارداد مرتبط) و estimated_hours "
    "(یک عدد صحیح واقع‌بینانه از نفر-ساعت لازم برای ارائه آن بخش) برگردانید. فقط یک "
    "آرایه JSON از این اشیاء را بدون هیچ توضیح یا نشانه مارک‌داون برگردانید. دامنه‌ای "
    "را که از متن برداشت نمی‌شود اختراع نکنید."
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
        category = str(item.get("category") or "other").strip().lower()
        if category not in CATEGORIES:
            category = "other"
        role = str(item.get("role") or roles[0]).strip().lower()
        if role not in roles:
            role = roles[0]
        try:
            hours = float(item.get("estimated_hours") or 0)
        except (TypeError, ValueError):
            hours = 0.0
        sections.append({
            "order_index": i,
            "title": str(item["title"]).strip()[:300],
            "category": category,
            "role": role,
            "excerpt": str(item.get("excerpt") or "").strip()[:280],
            "estimated_hours": max(0.0, round(hours, 1)),
        })
    if not sections:
        raise AnalysisError("The model returned no usable sections.")
    return sections


_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*)$", re.MULTILINE)


def split_sections_heuristic(text: str, coefficients: dict) -> list[dict]:
    """Offline fallback (no LLM configured): split on markdown headings, or on
    blank-line-separated paragraphs if the document has none. Applies a flat,
    word-count-based estimate so the workflow still produces an editable
    starting point without any AI provider configured."""
    roles = _roles_from_coefficients(coefficients)
    role = roles[0]
    matches = [m for m in _HEADING_RE.finditer(text) if not m.group(2).strip().lower().startswith("page ")]
    chunks: list[tuple[str, str]] = []
    if matches:
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            chunks.append((m.group(2).strip(), text[start:end].strip()))
    if not chunks:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        for i, p in enumerate(paragraphs[:40], 1):
            first_line = p.splitlines()[0][:80].strip()
            chunks.append((first_line or f"Section {i}", p))

    sections = []
    for i, (title, body) in enumerate(chunks):
        if not body:
            continue
        words = len(body.split())
        hours = max(4.0, round(words / 40, 1))  # rough: ~40 words of scoped text per person-hour
        sections.append({
            "order_index": i,
            "title": (title or f"Section {i + 1}")[:300],
            "category": "other",
            "role": role,
            "excerpt": body[:280],
            "estimated_hours": hours,
        })
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
