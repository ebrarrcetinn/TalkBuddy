# Başlangıç kelime değerlendirmesinin kurallarını test eder: havuz, bölüm, eşik, öneri.
import random

from app.assessment import (
    LEVELS,
    SECTION_SIZE,
    build_pool,
    build_sections,
    evaluate,
    is_ready,
    passes,
)
from app.wordlist import Entry
from tests.fakes import fake_entries


def selections(*counts: int) -> list[list[str]]:
    return [[f"w{i}" for i in range(count)] for count in counts]


def test_each_level_gets_its_own_shuffled_section_of_30_words():
    pool = build_pool(fake_entries())
    sections = build_sections(pool, random.Random(1))
    levels = {entry.word: entry.level for words in pool.values() for entry in words}

    assert len(sections) == len(LEVELS) == 5
    for level, words in zip(LEVELS, sections, strict=True):
        assert len(words) == SECTION_SIZE
        assert len(set(words)) == SECTION_SIZE
        assert {levels[word] for word in words} == {level}
        assert words != sorted(words)


def test_sections_follow_the_part_of_speech_quota():
    pool = build_pool(fake_entries())
    pos = {entry.word: entry.pos for words in pool.values() for entry in words}

    for words in build_sections(pool, random.Random(2)):
        counts = {kind: sum(pos[word] == kind for word in words) for kind in set(pos.values())}
        assert counts == {"noun": 12, "verb": 8, "adjective": 6, "adverb": 4}


def test_pool_keeps_single_content_words_at_their_lowest_level():
    entries = [
        Entry("light", "noun", "A1"),
        Entry("light", "verb", "B1"),
        Entry("ice cream", "noun", "A1"),
        Entry("the", "determiner", "A1"),
        Entry("go", "verb", "A1"),
        Entry("ubiquitous", "adjective", "C2"),
        Entry("mine", "pronoun", "A2"),
        Entry("mine", "noun", "B1"),
    ]

    pool = build_pool(entries)

    assert [entry.word for entry in pool["A1"]] == ["light"]
    assert pool["A2"] == []
    assert pool["B1"] == []
    assert all(entry.word != "ubiquitous" for words in pool.values() for entry in words)


def test_pool_is_not_ready_without_a_word_list():
    assert not is_ready(build_pool([]))
    assert is_ready(build_pool(fake_entries()))


def test_threshold_is_29_of_30():
    assert not passes(28)
    assert passes(29)
    assert passes(30)


def test_recommends_highest_consecutive_passed_level():
    result = evaluate(selections(30, 29, 29, 20, 10))

    assert result.recommended_level == "B1"
    assert not result.inconsistent
    assert [score.passed for score in result.scores] == [True, True, True, False, False]


def test_a1_is_recommended_when_a1_is_not_passed():
    assert evaluate(selections(28, 0, 0, 0, 0)).recommended_level == "A1"


def test_all_sections_passed_recommends_c1():
    assert evaluate(selections(30, 30, 29, 30, 29)).recommended_level == "C1"


def test_high_upper_levels_after_a_gap_are_inconsistent():
    result = evaluate(selections(30, 10, 30, 30, 0))

    assert result.recommended_level == "A1"
    assert result.inconsistent
