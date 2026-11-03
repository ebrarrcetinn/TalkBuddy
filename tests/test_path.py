# Başlangıç rotasını ve günün önerilen konuşmasını test eder.
from app.path import STARTER_PATH, suggest


def test_beginners_follow_the_starter_path_in_order():
    first = suggest("A1", set(), [], None)
    assert (first.kind, first.lesson, first.step, first.minutes) == ("lesson", "starter-1", 1, 5)

    second = suggest("A2", {"starter-1"}, [], None)
    assert (second.lesson, second.step, second.minutes) == ("starter-2", 2, 10)


def test_after_the_path_or_from_b1_interests_rotate():
    done = {lesson.key for lesson in STARTER_PATH}
    assert suggest("A1", done, ["Spor", "Müzik"], None).topic == "Spor"
    assert suggest("B2", set(), ["Spor", "Müzik"], "Spor").topic == "Müzik"
    assert suggest("B2", set(), ["Spor", "Müzik"], "Müzik").topic == "Spor"


def test_without_interests_free_talk_is_suggested():
    assert suggest("C1", set(), [], None).kind == "free"
