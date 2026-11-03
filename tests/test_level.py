# Seviye motorunun tek mesajla zıplamadığını ve kelime seviyesini doğru okuduğunu test eder.
from app import wordlist
from app.level import LevelState, LexicalProfile, update
from app.wordlist import Entry


def test_undetermined_estimate_keeps_state():
    state = LevelState(score=3.0, level="B1")

    assert update(state, "Undetermined", None) == state


def test_first_estimate_is_accepted():
    assert update(LevelState(), "A2", None).level == "A2"


def test_single_high_estimate_does_not_change_level():
    state = LevelState(score=3.0, level="B1")

    assert update(state, "C1", None).level == "B1"


def test_level_changes_after_consistent_estimates():
    state = LevelState(score=3.0, level="B1")
    levels = []
    for _ in range(5):
        state = update(state, "B2", None)
        levels.append(state.level)

    assert levels[0] == "B1"
    assert levels[-1] == "B2"


def test_lexical_score_uses_most_advanced_words():
    lexicon = LexicalProfile(
        {"i": "A1", "think": "A1", "the": "A1", "plan": "A1", "is": "A1", "ambiguous": "C1"}
    )

    assert lexicon.score("I think the plan is ambiguous") == (5 + 1 + 1) / 3


def test_lexical_score_needs_enough_words():
    lexicon = LexicalProfile({"yes": "A1"})

    assert lexicon.score("yes") is None


def test_lexical_profile_strips_common_suffixes():
    lexicon = LexicalProfile({"study": "A1", "walk": "A1", "make": "A1"})

    assert lexicon.level_of("studies") == "A1"
    assert lexicon.level_of("walked") == "A1"
    assert lexicon.level_of("making") == "A1"


def test_word_list_uses_the_lowest_level_of_a_word(tmp_path):
    path = tmp_path / "words.csv"
    entries = [
        Entry("light", "noun", "A1"),
        Entry("light", "verb", "B1"),
        Entry("vivid", "adjective", "C1"),
    ]
    wordlist.save(entries, path)

    lexicon = LexicalProfile.from_entries(wordlist.load(path))

    assert lexicon.level_of("lights") == "A1"
    assert lexicon.level_of("vivid") == "C1"


def test_missing_word_list_gives_empty_profile(tmp_path):
    lexicon = LexicalProfile.from_entries(wordlist.load(tmp_path / "missing.csv"))

    assert lexicon.score("I really like going to school with my friends") is None
