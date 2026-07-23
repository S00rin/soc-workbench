"""Tests for the multi-language (English/Farsi) help guide seed data and the
audience visibility rule used by the help router."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.help import HelpGuide
from app.routers.help import _visible
from app.services.help_guides import seed_default_guides


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_seed_creates_matched_english_and_farsi_pairs(db):
    seed_default_guides(db)
    rows = db.query(HelpGuide).all()
    assert rows
    slugs_by_language: dict[str, set[str]] = {"en": set(), "fa": set()}
    for row in rows:
        slugs_by_language[row.language].add(row.slug)
        assert row.title.strip()
        assert row.content.strip()
    assert slugs_by_language["en"] == slugs_by_language["fa"]  # every guide exists in both languages


def test_seed_includes_at_least_one_user_and_one_admin_guide(db):
    seed_default_guides(db)
    audiences = {row.audience for row in db.query(HelpGuide).all()}
    assert audiences == {"user", "admin"}


def test_seed_is_idempotent_and_preserves_edits(db):
    seed_default_guides(db)
    row = db.query(HelpGuide).filter(HelpGuide.slug == "getting-started", HelpGuide.language == "en").first()
    row.content = "Edited by an admin."
    db.commit()

    seed_default_guides(db)  # simulate a restart re-running the seed

    total_before = db.query(HelpGuide).count()
    seed_default_guides(db)
    assert db.query(HelpGuide).count() == total_before  # no duplicate rows inserted
    reloaded = db.query(HelpGuide).filter(HelpGuide.slug == "getting-started", HelpGuide.language == "en").first()
    assert reloaded.content == "Edited by an admin."  # the seed never overwrites an existing row


def test_admin_guides_are_hidden_from_non_admin_roles(db):
    seed_default_guides(db)
    admin_guide = db.query(HelpGuide).filter(HelpGuide.audience == "admin").first()
    user_guide = db.query(HelpGuide).filter(HelpGuide.audience == "user").first()
    assert _visible(admin_guide, "analyst") is False
    assert _visible(admin_guide, "admin") is True
    assert _visible(user_guide, "analyst") is True
    assert _visible(user_guide, "admin") is True
