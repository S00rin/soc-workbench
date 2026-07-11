"""Extract text/markdown from many input formats (Module 2).

Keeps headings, tables, lists, and code blocks where the source format allows.
Extraction failures raise ExtractionError with a clear message.
"""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from ..logging_config import get_logger

logger = get_logger(__name__)


class ExtractionError(Exception):
    pass


def _from_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover
        raise ExtractionError("pypdf not installed") from e
    reader = PdfReader(str(path))
    parts = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if text.strip():
            parts.append(f"\n\n## Page {i}\n\n{text.strip()}")
    if not parts:
        raise ExtractionError(
            "No extractable text in PDF (it may be scanned images; OCR not enabled)."
        )
    return "".join(parts).strip()


def _from_docx(path: Path) -> str:
    from docx import Document as Docx  # python-docx

    doc = Docx(str(path))
    lines: list[str] = []
    for para in doc.paragraphs:
        style = (para.style.name or "").lower()
        text = para.text.strip()
        if not text:
            continue
        if style.startswith("heading"):
            level = "".join(c for c in style if c.isdigit()) or "2"
            lines.append(f"{'#' * min(int(level), 6)} {text}")
        else:
            lines.append(text)
    for table in doc.tables:
        rows = [[c.text.strip() for c in row.cells] for row in table.rows]
        if rows:
            lines.append(_table_to_md(rows))
    if not lines:
        raise ExtractionError("DOCX contained no readable text.")
    return "\n\n".join(lines)


def _from_xlsx(path: Path) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(str(path), read_only=True, data_only=True)
    blocks: list[str] = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = ["" if v is None else str(v) for v in row]
            if any(c.strip() for c in cells):
                rows.append(cells)
        if rows:
            blocks.append(f"## Sheet: {ws.title}\n\n{_table_to_md(rows)}")
    wb.close()
    if not blocks:
        raise ExtractionError("Workbook had no data.")
    return "\n\n".join(blocks)


def _from_pptx(path: Path) -> str:
    from pptx import Presentation

    prs = Presentation(str(path))
    slides: list[str] = []
    for i, slide in enumerate(prs.slides, 1):
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame and shape.text_frame.text.strip():
                texts.append(shape.text_frame.text.strip())
        if texts:
            slides.append(f"## Slide {i}\n\n" + "\n\n".join(texts))
    if not slides:
        raise ExtractionError("Presentation had no text.")
    return "\n\n".join(slides)


def _from_html(raw: str) -> str:
    from bs4 import BeautifulSoup
    from markdownify import markdownify

    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    body = soup.body or soup
    return markdownify(str(body), heading_style="ATX").strip()


def _from_csv(raw: str) -> str:
    reader = csv.reader(io.StringIO(raw))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        raise ExtractionError("CSV had no rows.")
    return _table_to_md(rows)


def _from_json(raw: str) -> str:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"Invalid JSON: {e}") from e
    return "```json\n" + json.dumps(obj, indent=2, ensure_ascii=False) + "\n```"


def _table_to_md(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = [r + [""] * (width - len(r)) for r in rows]
    header = norm[0]
    md = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * width) + " |"]
    for r in norm[1:]:
        md.append("| " + " | ".join(cell.replace("|", "\\|") for cell in r) + " |")
    return "\n".join(md)


EXT_MAP = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".pptx": "pptx",
    ".html": "html",
    ".htm": "html",
    ".csv": "csv",
    ".json": "json",
    ".md": "text",
    ".markdown": "text",
    ".txt": "text",
    ".log": "text",
}


def extract_file(path: Path) -> str:
    """Extract markdown-ish text from a file on disk."""
    ext = path.suffix.lower()
    kind = EXT_MAP.get(ext)
    if kind is None:
        # Best effort: try as UTF-8 text.
        kind = "text"
    try:
        if kind == "pdf":
            return _from_pdf(path)
        if kind == "docx":
            return _from_docx(path)
        if kind == "xlsx":
            return _from_xlsx(path)
        if kind == "pptx":
            return _from_pptx(path)
        raw = path.read_text(encoding="utf-8", errors="replace")
        if kind == "html":
            return _from_html(raw)
        if kind == "csv":
            return _from_csv(raw)
        if kind == "json":
            return _from_json(raw)
        return raw.strip()
    except ExtractionError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("Extraction failed for %s", path.name)
        raise ExtractionError(f"Could not extract {path.name}: {e}") from e


def extract_text(raw: str, kind: str = "text") -> str:
    """Extract from an in-memory string (kind: text/html/csv/json/markdown)."""
    kind = kind.lower()
    if kind == "html":
        return _from_html(raw)
    if kind == "csv":
        return _from_csv(raw)
    if kind == "json":
        return _from_json(raw)
    return raw.strip()
