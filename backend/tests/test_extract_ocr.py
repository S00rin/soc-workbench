"""Tests for OCR extraction of image files and scanned (text-layer-free) PDFs.

The OCR tests skip automatically when the Tesseract engine isn't installed, so
they run locally (and in any image that has tesseract) without breaking CI,
which doesn't install the native engine.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.services import extract

_OCR_READY, _OCR_REASON = extract._ocr_ready()
requires_ocr = pytest.mark.skipif(not _OCR_READY, reason=f"OCR engine unavailable: {_OCR_REASON}")


def test_image_extensions_route_to_ocr():
    for ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"):
        assert extract.EXT_MAP[ext] == "image"


def test_clean_ocr_text_drops_blank_lines_and_trims():
    raw = "  Contract scope  \n\n\n  design and build  \n   \n"
    assert extract._clean_ocr_text(raw) == "Contract scope\ndesign and build"


def _render_text_image(path: Path, text: str) -> None:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (900, 220), "white")
    draw = ImageDraw.Draw(image)
    candidates = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    )
    font_path = next((candidate for candidate in candidates if candidate.is_file()), None)
    font = ImageFont.truetype(str(font_path), 34) if font_path else ImageFont.load_default(size=34)
    draw.text((30, 40), text, fill="black", font=font, spacing=14)
    image.save(path)


@requires_ocr
def test_ocr_reads_text_from_an_image(tmp_path):
    img = tmp_path / "scan.png"
    _render_text_image(img, "Contract scope: website design\nand backend development.")
    out = extract.extract_file(img)
    assert "Contract scope" in out
    assert "backend development" in out


@requires_ocr
def test_scanned_pdf_without_text_layer_falls_back_to_ocr(tmp_path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    img = tmp_path / "scan.png"
    _render_text_image(img, "Scanned agreement scope of work")

    pdf = tmp_path / "scanned.pdf"
    c = canvas.Canvas(str(pdf), pagesize=A4)
    c.drawImage(str(img), 40, 500, width=500, height=120)  # image only — no text layer
    c.showPage()
    c.save()

    out = extract.extract_file(pdf)
    assert "## Page 1" in out
    assert "scope of work" in out.lower()


def test_ocr_ready_reports_a_reason_string_when_unavailable():
    ready, reason = extract._ocr_ready()
    # When unavailable the reason must be a non-empty, actionable message.
    assert ready or reason
