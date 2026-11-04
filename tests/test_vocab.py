# Aralıklı tekrar takviminin dokümandaki 1-3-7-14-30 gün kuralına uyduğunu test eder.
from datetime import date

import pytest

from app.vocab import is_sentence, next_review, status_for

TODAY = date(2026, 11, 1)


@pytest.mark.parametrize(
    ("review_count", "days"), [(0, 1), (1, 3), (2, 7), (3, 14), (4, 30), (9, 30)]
)
def test_review_intervals(review_count, days):
    assert (next_review(review_count, TODAY) - TODAY).days == days


@pytest.mark.parametrize(
    ("review_count", "status"),
    [(0, "NEW"), (1, "LEARNING"), (2, "LEARNING"), (3, "REVIEW"), (4, "REVIEW"), (5, "MASTERED")],
)
def test_status_follows_review_count(review_count, status):
    assert status_for(review_count) == status


@pytest.mark.parametrize(
    ("expression", "sentence"),
    [
        ("I'm from Turkey.", True),
        ("Where do you live?", True),
        ("borrow", False),
        ("give up", False),
        ("I'm looking forward to ...", False),
        ("How do you say ... in English?", False),
    ],
)
def test_full_sentences_are_told_apart_from_words_and_patterns(expression, sentence):
    assert is_sentence(expression) is sentence
