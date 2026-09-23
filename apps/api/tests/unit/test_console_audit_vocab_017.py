"""Spec 017 (R5.4, R11.5, R12.1): the two new actions leave a trail the
partner can read, and every audit category has a name in both languages
so the console can offer «filtrar por categoría»."""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.api.console import audit as audit_module

pytestmark = pytest.mark.asyncio

ACTIONS = ("console.capability.update", "console.billing.email_update")


async def test_the_new_actions_are_seeded_in_both_languages(db_session) -> None:
    rows = (
        await db_session.execute(
            sa.text(
                "SELECT action, category, summary_es, summary_en "
                "FROM console_audit_vocabulary WHERE action = ANY(:a)"
            ),
            {"a": list(ACTIONS)},
        )
    ).all()
    assert {r[0] for r in rows} == set(ACTIONS)
    for _, category, es, en in rows:
        assert category in audit_module.CATEGORY_LABELS
        assert "{actor}" in es and "{actor}" in en


async def test_every_seeded_category_has_a_label_in_both_languages(db_session) -> None:
    categories = {
        r[0]
        for r in (
            await db_session.execute(
                sa.text("SELECT DISTINCT category FROM console_audit_vocabulary")
            )
        ).all()
    }
    assert categories, "the vocabulary is empty: run the migrations"
    for category in categories:
        labels = audit_module.CATEGORY_LABELS.get(category)
        assert labels, f"category without label: {category}"
        assert labels["es"] and labels["en"]
