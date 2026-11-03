# Öğrenme planını test eder: ilerleme yüzdesi ve günün yeni kelimelerinin seçimi.
import random

from app.plan import LearningPlan
from tests.fakes import fake_entries


def test_progress_counts_known_and_learning_words():
    plan = LearningPlan(fake_entries())
    words = plan.words("A2")

    progress = plan.progress("A2", known=set(words[:20]), learning=set(words[15:30]))

    assert progress.total == len(words) == 80
    assert progress.known == 20
    assert progress.learning == 10
    assert progress.percent == 25


def test_no_plan_for_levels_outside_the_list():
    assert LearningPlan(fake_entries()).progress("C2", set(), set()) is None


def test_suggestions_skip_known_words_and_prefer_unticked_ones():
    plan = LearningPlan(fake_entries())
    words = plan.words("B1")
    prefer = set(words[40:43])

    exclude = set(words[:40])
    chosen = plan.suggest("B1", exclude=exclude, prefer=prefer, count=5, rng=random.Random(1))

    assert len(chosen) == 5
    assert set(chosen[:3]) == prefer
    assert not set(chosen) & set(words[:40])
