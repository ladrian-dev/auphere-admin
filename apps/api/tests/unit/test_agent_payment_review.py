"""Spec 025: the reviewer list lives in ``policies.payment_review``."""

from __future__ import annotations

import pytest

from nexus_api.services.agent_payment_review import (
    MAX_REVIEWERS,
    Reviewer,
    ReviewerInvalidPhone,
    TooManyReviewers,
    apply_reviewers,
    reviewers_of,
)


def test_no_policy_means_no_reviewers() -> None:
    assert reviewers_of(None) == []
    assert reviewers_of({"payment_review": "garbage"}) == []


def test_reviewers_are_normalised_deduplicated_and_keep_their_name() -> None:
    out = apply_reviewers(
        {"llm": {"respond_model": "x"}},
        [
            Reviewer(phone="+56 9 9128 0655", name=" Daniela "),
            Reviewer(phone="56991280655", name="otra vez"),
            Reviewer(phone="+56989829063"),
        ],
    )
    assert out["llm"] == {"respond_model": "x"}  # the rest of the policies survive
    assert out["payment_review"]["reviewers"] == [
        {"phone": "+56991280655", "name": "Daniela"},
        {"phone": "+56989829063", "name": None},
    ]
    assert [r.phone for r in reviewers_of(out)] == ["+56991280655", "+56989829063"]


def test_a_phone_that_could_never_match_is_refused_by_name() -> None:
    with pytest.raises(ReviewerInvalidPhone) as exc:
        apply_reviewers({}, [Reviewer(phone="12")])
    assert exc.value.code == "payment_reviewer_invalid_phone"
    assert exc.value.phone == "12"


def test_an_empty_list_turns_the_review_off() -> None:
    out = apply_reviewers({"payment_review": {"reviewers": [{"phone": "+56991280655"}]}}, [])
    assert reviewers_of(out) == []


def test_at_most_ten_reviewers() -> None:
    many = [Reviewer(phone=f"+5699128{n:04d}") for n in range(MAX_REVIEWERS + 1)]
    with pytest.raises(TooManyReviewers):
        apply_reviewers({}, many)
