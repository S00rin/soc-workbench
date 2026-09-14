"""Markdown → PDF for reports and the executive brief (EN + FA)."""
from __future__ import annotations

import glob
import re
from pathlib import Path

from ..logging_config import get_logger

logger = get_logger(__name__)

_RTL_FONT_CANDIDATES = [
    "*Vazirmatn*Regular*.ttf", "*Vazir*.ttf", "*NotoNaskhArabic*Regular*.ttf",
    "*NotoNaskhArabic*.ttf", "*NotoSansArabic*Regular*.ttf", "*NotoSansArabic*.ttf", "*Amiri*Regular*.ttf",
]
_RTL_FONT_DIRS = ["/usr/share/fonts", "/usr/local/share/fonts", str(Path.home() / ".fonts"), str(Path.home() / ".local/share/fonts")]
_rtl_font_name_cache: str | None = None
_rtl_font_resolved = False


def shape_for_pdf(text: str, language: str) -> str:
    if language != "fa" or not text:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(text))
    except ImportError:
        return text


def register_rtl_font() -> str | None:
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
                    pdfmetrics.registerFont(TTFont("SocWorkbenchRTL", path))
                    _rtl_font_name_cache = "SocWorkbenchRTL"
                    logger.info("Registered Persian-capable PDF font from %s", path)
                    return _rtl_font_name_cache
                except Exception:  # noqa: BLE001
                    continue
    logger.warning("No Persian-capable font found for PDF export; Farsi glyphs may not render.")
    return None


def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(text: str) -> str:
    text = _escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", text)
    return text


def _parse_table(lines: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in lines:
        if re.match(r"^\s*\|?\s*:?-{3,}", line.replace(" ", "")):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells:
            rows.append(cells)
    return rows


def export_markdown_pdf(content: str, out_dir: Path, name: str, title: str = "", language: str = "en") -> Path:
    """Render Markdown (headings, lists, tables, paragraphs) to a real PDF."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.pdf"
    rtl = language == "fa"
    font_name = register_rtl_font() if rtl else None
    base_font = font_name or "Helvetica"
    bold_font = font_name or "Helvetica-Bold"
    align = TA_RIGHT if rtl else TA_LEFT
    styles = getSampleStyleSheet()

    def styled(name_: str, parent: str, **kwargs) -> ParagraphStyle:
        kwargs.setdefault("fontName", base_font)
        kwargs.setdefault("alignment", align)
        kwargs.setdefault("leading", kwargs.get("fontSize", 10) * 1.4)
        return ParagraphStyle(name_, parent=styles[parent], **kwargs)

    h1 = styled("H1", "Heading1", fontName=bold_font, fontSize=16, spaceAfter=8)
    h2 = styled("H2", "Heading2", fontName=bold_font, fontSize=13, spaceBefore=10, spaceAfter=6)
    h3 = styled("H3", "Heading3", fontName=bold_font, fontSize=11, spaceBefore=8, spaceAfter=4)
    body = styled("Body", "Normal", fontSize=9, spaceAfter=4)
    muted = styled("Muted", "Normal", fontSize=8, textColor=colors.HexColor("#5b6573"))

    def p(text: str, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(shape_for_pdf(_inline(text), language), style)

    story: list = []
    if title:
        story.append(p(title, h1))
        story.append(Spacer(1, 4 * mm))

    lines = (content or "").splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        if not line.strip():
            i += 1
            continue
        if line.startswith("|") and "|" in line[1:]:
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            data = [[p(cell, body) for cell in row] for row in _parse_table(block)]
            if data:
                table = Table(data, hAlign="RIGHT" if rtl else "LEFT")
                table.setStyle(TableStyle([
                    ("FONTNAME", (0, 0), (-1, 0), bold_font),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c5ced8")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("ALIGN", (0, 0), (-1, -1), "RIGHT" if rtl else "LEFT"),
                ]))
                story.append(table)
                story.append(Spacer(1, 3 * mm))
            continue
        if line.startswith("# "):
            story.append(p(line[2:], h1)); i += 1; continue
        if line.startswith("## "):
            story.append(p(line[3:], h2)); i += 1; continue
        if line.startswith("### "):
            story.append(p(line[4:], h3)); i += 1; continue
        if line.startswith(("- ", "* ")):
            items = []
            while i < len(lines) and lines[i].lstrip().startswith(("- ", "* ")):
                items.append(ListItem(p(lines[i].lstrip()[2:], body), leftIndent=12))
                i += 1
            story.append(ListFlowable(items, bulletType="bullet"))
            continue
        if line.startswith("_") and line.endswith("_") and len(line) > 2:
            story.append(p(line.strip("_"), muted)); i += 1; continue
        story.append(p(line, body))
        i += 1

    doc = SimpleDocTemplate(
        str(path), pagesize=A4, title=title or name,
        leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
    )
    doc.build(story)
    return path
