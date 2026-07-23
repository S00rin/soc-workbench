"""Tests for the project price analyzer: section splitting, cost math, WBS
generation/scheduling, RACI suggestion and export."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.price_analyzer import Contract, ContractSection, DEFAULT_COEFFICIENTS, WBSItem
from app.services import price_analyzer as pa

SAMPLE_CONTRACT = """## Requirements gathering
We will interview stakeholders and document functional requirements across
three departments, producing a signed-off requirements specification.

## Design
UI/UX design for the new website including wireframes and high fidelity
mockups for every page in scope.

## Development
Build the responsive frontend and the backend API using the agreed stack,
covering all pages and integrations described above.

## Testing
QA test plan authoring, execution, and bug fixing prior to release.
"""


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_heuristic_split_produces_editable_sections_without_any_llm():
    sections = pa.split_sections_heuristic(SAMPLE_CONTRACT, DEFAULT_COEFFICIENTS)
    assert len(sections) == 4
    assert {s["title"] for s in sections} == {"Requirements gathering", "Design", "Development", "Testing"}
    assert all(s["estimated_hours"] >= 4.0 for s in sections)
    assert all(s["role"] == "project_manager" for s in sections)  # first configured role is the fallback


def test_heuristic_split_falls_back_to_paragraphs_without_headings():
    text = "First scope paragraph about onboarding.\n\nSecond scope paragraph about migration."
    sections = pa.split_sections_heuristic(text, DEFAULT_COEFFICIENTS)
    assert len(sections) == 2


def test_heuristic_split_rejects_empty_document():
    with pytest.raises(pa.AnalysisError):
        pa.split_sections_heuristic("   \n   ", DEFAULT_COEFFICIENTS)


def test_compute_costs_applies_overhead_contingency_tax_and_discount():
    coefficients = {
        "currency": "USD", "rates": {"developer": 50.0}, "overhead_percent": 10,
        "contingency_percent": 10, "tax_percent": 9, "discount_percent": 5,
    }
    section = {"id": 1, "title": "Build", "category": "development", "role": "developer",
               "adjusted_hours": 100.0, "hourly_rate_override": None}
    cost = pa.compute_costs([section], coefficients)
    assert cost["subtotal"] == 5000.0
    assert cost["overhead_amount"] == 500.0
    # contingency is applied on (subtotal + overhead)
    assert cost["contingency_amount"] == pytest.approx(550.0)
    pre_discount = 5000.0 + 500.0 + 550.0
    discount = pre_discount * 0.05
    taxable = pre_discount - discount
    tax = taxable * 0.09
    assert cost["discount_amount"] == pytest.approx(discount, abs=0.01)
    assert cost["tax_amount"] == pytest.approx(tax, abs=0.01)
    assert cost["total"] == pytest.approx(taxable + tax, abs=0.01)


def test_compute_costs_honors_per_section_rate_override():
    coefficients = {"rates": {"developer": 50.0}, "overhead_percent": 0, "contingency_percent": 0, "tax_percent": 0, "discount_percent": 0}
    section = {"id": 1, "title": "Special", "category": "development", "role": "developer",
               "adjusted_hours": 10.0, "hourly_rate_override": 120.0}
    cost = pa.compute_costs([section], coefficients)
    assert cost["rows"][0]["rate"] == 120.0
    assert cost["total"] == 1200.0


def test_generate_wbs_is_three_levels_project_phase_task(db):
    contract = Contract(title="Website Revamp", coefficients=dict(DEFAULT_COEFFICIENTS))
    db.add(contract)
    db.commit()
    sections = []
    for i, (title, category) in enumerate([("Reqs", "requirements"), ("UI", "design"), ("Build", "development")]):
        row = ContractSection(contract_id=contract.id, order_index=i, title=title, category=category,
                               role="developer", estimated_hours=8, adjusted_hours=8)
        db.add(row)
        sections.append(row)
    db.commit()

    items = pa.generate_wbs(contract.title, sections, "en")
    levels = {item["level"] for item in items}
    assert levels == {1, 2, 3}
    root = next(i for i in items if i["level"] == 1)
    assert root["code"] == "1"
    phases = [i for i in items if i["level"] == 2]
    assert len(phases) == 3  # requirements, design, development each get their own phase
    tasks = [i for i in items if i["level"] == 3]
    assert len(tasks) == 3
    assert all(t["code"].count(".") == 2 for t in tasks)  # e.g. "1.1.1"


def test_schedule_wbs_runs_tasks_sequentially_from_start_date():
    from datetime import timedelta

    rows = [
        {"id": 1, "parent_id": None, "level": 1, "order_index": 0, "section_id": None},
        {"id": 2, "parent_id": 1, "level": 2, "order_index": 0, "section_id": None},
        {"id": 3, "parent_id": 2, "level": 3, "order_index": 0, "section_id": 10},
        {"id": 4, "parent_id": 2, "level": 3, "order_index": 1, "section_id": 20},
    ]
    hours_by_section = {10: 16.0, 20: 8.0}  # 2 days then 1 day at 8h/day
    schedule = pa.schedule_wbs(rows, hours_by_section, hours_per_day=8.0, start="2026-01-05")
    first, second = schedule[3], schedule[4]
    assert first["start"].isoformat() == "2026-01-05"
    assert first["duration"] == 2.0
    # second task starts the day right after the first one ends
    assert second["start"] == first["end"] + timedelta(days=1)

    # the phase (level 2) and project (level 1) spans cover both tasks
    project_span, phase_span = schedule[1], schedule[2]
    assert project_span["start"] == phase_span["start"] == first["start"]
    assert project_span["end"] == phase_span["end"] == second["end"]


def test_suggest_raci_assigns_accountable_and_responsible_per_task():
    rows = [
        {"id": 1, "level": 1}, {"id": 2, "level": 2}, {"id": 3, "level": 3}, {"id": 4, "level": 3},
    ]
    entries = pa.suggest_raci(rows)
    assert len(entries) == 4  # 2 entries per level-3 task, 2 tasks
    for wbs_item_id in (3, 4):
        codes = {e["raci"] for e in entries if e["wbs_item_id"] == wbs_item_id}
        assert codes == {"A", "R"}


def test_shape_for_pdf_only_reorders_farsi_text():
    assert pa.shape_for_pdf("Hello", "en") == "Hello"
    shaped = pa.shape_for_pdf("سلام دنیا", "fa")
    assert shaped  # reshaped/bidi text is non-empty and need not equal the logical-order input
    assert shaped != ""


def test_export_excel_and_pdf_produce_non_empty_files(tmp_path, db):
    contract = Contract(title="Website Revamp", customer="Acme", language="en", coefficients=dict(DEFAULT_COEFFICIENTS))
    db.add(contract)
    db.commit()
    db.refresh(contract)
    cost = {
        "currency": "USD", "total_hours": 10.0, "subtotal": 500.0, "overhead_amount": 50.0,
        "contingency_amount": 55.0, "discount_amount": 0.0, "tax_amount": 0.0, "total": 605.0,
        "rows": [{"section_id": 1, "title": "Design", "category": "design", "role": "designer", "hours": 10.0, "rate": 50.0, "cost": 500.0}],
    }
    wbs = [{"id": 1, "code": "1", "level": 1, "title": "Website Revamp", "start_date": "2026-01-05",
            "end_date": "2026-01-06", "duration_days": 2, "percent_complete": 0, "assignee": ""}]
    raci = [{"wbs_item_id": 1, "participant": "Project Manager", "raci": "A"}]

    xlsx_path = pa.export_excel(contract, cost, wbs, raci, tmp_path, "export-test")
    assert xlsx_path.exists() and xlsx_path.stat().st_size > 0

    pdf_path = pa.export_pdf(contract, cost, wbs, raci, tmp_path, "export-test")
    assert pdf_path.exists() and pdf_path.stat().st_size > 0


def test_export_pdf_handles_farsi_contract_without_crashing(tmp_path):
    contract = Contract(title="قرارداد طراحی وب‌سایت", customer="شرکت الف", language="fa", coefficients=dict(DEFAULT_COEFFICIENTS))
    cost = {
        "currency": "IRR", "total_hours": 5.0, "subtotal": 250.0, "overhead_amount": 0.0,
        "contingency_amount": 0.0, "discount_amount": 0.0, "tax_amount": 0.0, "total": 250.0,
        "rows": [{"section_id": 1, "title": "طراحی", "category": "design", "role": "designer", "hours": 5.0, "rate": 50.0, "cost": 250.0}],
    }
    wbs = [{"id": 1, "code": "1", "level": 1, "title": "قرارداد طراحی وب‌سایت", "start_date": "2026-01-05",
            "end_date": "2026-01-05", "duration_days": 1, "percent_complete": 0, "assignee": ""}]
    raci = [{"wbs_item_id": 1, "participant": "مدیر پروژه", "raci": "A"}]
    pdf_path = pa.export_pdf(contract, cost, wbs, raci, tmp_path, "fa-export-test")
    assert pdf_path.exists() and pdf_path.stat().st_size > 0
