# Öğrenme akışını test eder: hafıza, kelime kutusu, hata takibi, seviye ve oturum raporu.
from datetime import UTC, datetime

import pytest

from app.db import Database
from app.plan import LearningPlan
from app.schemas import Persona
from app.tutor import SessionNotFound
from tests.fakes import FakeClock, FakeLLM, coach_json, fake_entries, make_tutor

LEARNER = "learner-0001"

CORRECTION = {
    "latest_error": "I go",
    "corrected_version": "I went",
    "focus_area": "Past simple",
    "repeated_errors": [],
}


def test_learner_without_level_is_not_tested(tmp_path):
    llm = FakeLLM(coach_json())

    make_tutor(tmp_path, llm).start(LEARNER, Persona.FEMALE)

    system = llm.calls[0][0]
    assert "new learner, no saved level" in system
    assert "do not run a test" in system


def test_session_survives_restart(tmp_path):
    first = make_tutor(tmp_path, FakeLLM(coach_json("Welcome!")))
    session_id = first.start(LEARNER, Persona.FEMALE).session_id

    llm = FakeLLM(coach_json("Nice answer."))
    second = make_tutor(tmp_path, llm)
    result = second.reply(session_id, "happy means feeling good")

    assert result.response.spoken_text == "Nice answer."
    assert [m["role"] for m in llm.calls[0][1]] == ["user", "assistant", "user"]


def test_ended_session_cannot_continue(tmp_path):
    tutor = make_tutor(tmp_path, FakeLLM(coach_json(), coach_json("Bye")))
    session_id = tutor.start(LEARNER, Persona.MALE).session_id
    tutor.end(session_id)

    with pytest.raises(SessionNotFound):
        tutor.reply(session_id, "hello")


def test_words_patterns_and_sentences_are_saved(tmp_path):
    entries = ["crowded", "It depends on ...", "Istanbul is beautiful, but it's very crowded."]
    tutor = make_tutor(tmp_path, FakeLLM(coach_json(VOCAB_BOX_UPDATE=entries)))

    result = tutor.start(LEARNER, Persona.FEMALE)

    assert result.new_words == entries
    assert {w["expression"] for w in tutor.vocabulary(LEARNER)} == set(entries)


def test_saved_words_get_their_turkish_meaning(tmp_path):
    tutor = make_tutor(
        tmp_path,
        FakeLLM(
            coach_json(),
            '{"turkish_meaning": "kalabalık", "example": "The bus is crowded."}',
            "not json",
            "still not json",
        ),
    )
    tutor.start(LEARNER, Persona.FEMALE)
    tutor.explain_word(LEARNER, "crowded", "It is very crowded.")

    tutor.save_word(LEARNER, "crowded")
    tutor.save_word(LEARNER, "noisy")
    tutor.fill_meanings(LEARNER)

    meanings = {w["expression"]: w["turkish_meaning"] for w in tutor.vocabulary(LEARNER)}
    assert meanings == {"crowded": "kalabalık", "noisy": None}


def test_vocabulary_is_saved_once_and_scheduled(tmp_path):
    words = [{"expression": "borrow", "turkish_meaning": "ödünç almak"}]
    tutor = make_tutor(
        tmp_path,
        FakeLLM(
            coach_json(VOCAB_BOX_UPDATE=words),
            coach_json(VOCAB_BOX_UPDATE=["Borrow"]),
        ),
    )

    first = tutor.start(LEARNER, Persona.FEMALE)
    second = tutor.reply(first.session_id, "add this word")

    assert first.new_words == ["borrow"]
    assert second.new_words == []
    [word] = tutor.vocabulary(LEARNER)
    assert word["status"] == "NEW"
    assert word["next_review"] == "2026-11-02"


def test_review_advances_only_when_due(tmp_path):
    clock = FakeClock()
    reviewed = {"reviewed_vocabulary": ["borrow"]}
    tutor = make_tutor(
        tmp_path,
        FakeLLM(
            coach_json(VOCAB_BOX_UPDATE=["borrow"]),
            coach_json(MEMORY_UPDATE=reviewed),
            coach_json(MEMORY_UPDATE=reviewed),
        ),
        clock,
    )
    session_id = tutor.start(LEARNER, Persona.FEMALE).session_id

    tutor.reply(session_id, "i borrow a book")
    assert tutor.vocabulary(LEARNER)[0]["review_count"] == 0

    clock.advance(days=1)
    tutor.reply(session_id, "i borrowed a book")
    [word] = tutor.vocabulary(LEARNER)
    assert word["review_count"] == 1
    assert word["status"] == "LEARNING"
    assert word["next_review"] == "2026-11-05"


def test_errors_and_weaknesses_reach_next_session(tmp_path):
    llm = FakeLLM(
        coach_json(CURRENT_LEVEL="A2"),
        coach_json(ERROR_TRACKING=CORRECTION),
        coach_json(ERROR_TRACKING=CORRECTION),
        coach_json("Summary", MEMORY_UPDATE={"session_summary": "Practised the past."}),
        coach_json("Welcome back!"),
    )
    tutor = make_tutor(tmp_path, llm)
    session_id = tutor.start(LEARNER, Persona.FEMALE).session_id
    tutor.reply(session_id, "yesterday i go to school")
    tutor.reply(session_id, "yesterday i go school")
    tutor.end(session_id)

    tutor.start(LEARNER, Persona.FEMALE)
    system = llm.calls[-1][0]

    assert "returning learner" in system
    assert "Current working level: A2" in system
    assert "Previous session summary: Practised the past." in system
    assert "past simple (1)" in system
    assert '"I go" -> "I went"' in system


def test_end_returns_report(tmp_path):
    clock = FakeClock()
    tutor = make_tutor(
        tmp_path,
        FakeLLM(
            coach_json(CURRENT_LEVEL="A2", VOCAB_BOX_UPDATE=["borrow"]),
            coach_json(CURRENT_LEVEL="A2", ERROR_TRACKING=CORRECTION),
            coach_json("Great work today!", CURRENT_LEVEL="A2"),
        ),
        clock,
    )
    session_id = tutor.start(LEARNER, Persona.FEMALE).session_id
    clock.advance(minutes=4)
    tutor.reply(session_id, "yesterday i go to school")
    clock.advance(minutes=3)

    report = tutor.end(session_id).report

    assert report.minutes == 7
    assert report.turns == 1
    assert report.start_level is None
    assert report.end_level == "A2"
    assert [word.expression for word in report.new_words] == ["borrow"]
    assert report.corrections[0].correction == "I went"
    assert report.focus_areas == ["Past simple"]
    assert report.summary == "Great work today!"


# Konuşma sürerken koça yeniden selamlaşmaması söylenir; seçilen konu ilk mesajda iletilir.
def test_partner_does_not_greet_again_during_a_conversation(tmp_path):
    llm = FakeLLM(coach_json("Hi! Let's talk about travel."), coach_json("Great answer."))
    tutor = make_tutor(tmp_path, llm)

    session_id = tutor.start(LEARNER, Persona.FEMALE, topic="Seyahat").session_id
    tutor.reply(session_id, "I like trains")

    first, second = llm.calls[0][0], llm.calls[1][0]
    assert "Topic the learner chose for this conversation: Seyahat." in first
    assert "already in progress" not in first
    assert "already in progress" in second
    assert "Do not greet them" in second


# Plan kelimeleri ilk mesajda önerilir; süre dolmak üzereyken koça toparlaması söylenir.
def test_plan_words_and_time_limit_reach_the_partner(tmp_path):
    clock = FakeClock()
    llm = FakeLLM(coach_json("Hi!"), coach_json("Good."), coach_json("Let's wrap up."))
    tutor = make_tutor(tmp_path, llm, clock, plan=LearningPlan(fake_entries()))
    tutor.start(LEARNER, Persona.FEMALE)
    Database(tmp_path / "test.db").save_level(LEARNER, "A2", 2.0, None, 0)

    session_id = tutor.start(LEARNER, Persona.FEMALE, minutes=10).session_id
    first = llm.calls[1][0]
    assert "New words from the learner's level plan" in first
    assert "Planned length of this conversation: 10 minutes." in first
    assert "Reply length limit: 2 short sentences, about 20 words, one question." in first

    clock.advance(minutes=9)
    tutor.reply(session_id, "I am fine")
    later = llm.calls[2][0]
    assert "Time used so far: 9 of 10 minutes." in later
    assert "Time is nearly up" in later


def test_word_explanation_is_asked_once_and_cached(tmp_path):
    llm = FakeLLM('{"turkish_meaning": "yolculuk", "example": "The journey was long."}')
    tutor = make_tutor(tmp_path, llm)

    first = tutor.explain_word(LEARNER, "journey", "What a journey!")
    second = tutor.explain_word(LEARNER, "Journey", "Another journey.")

    assert first.turkish_meaning == second.turkish_meaning == "yolculuk"
    assert len(llm.calls) == 1


def test_monthly_review_has_its_own_instructions_and_length(tmp_path):
    llm = FakeLLM(coach_json("Welcome to your monthly review."))
    tutor = make_tutor(tmp_path, llm, plan=LearningPlan(fake_entries()))

    tutor.start(LEARNER, Persona.FEMALE, mode="monthly")

    system = llm.calls[0][0]
    assert "MONTHLY SPEAKING REVIEW, not a normal practice session" in system
    assert "Planned length of this conversation: 15 minutes." in system
    assert "New words from the learner's level plan" not in system


# Ses tanımanın diğer tahminleri koça iletilir; seviye hesabı yalnızca ana metinle yapılır.
def test_alternative_transcriptions_reach_the_partner(tmp_path):
    llm = FakeLLM(coach_json("Hi!"), coach_json("Nice to hear that."))
    tutor = make_tutor(tmp_path, llm)
    session_id = tutor.start(LEARNER, Persona.FEMALE).session_id

    tutor.reply(session_id, "my name is Josh", ["my name is Ebrar", "my name is Josh"])

    sent = llm.calls[1][1][-1]["content"]
    assert sent == "my name is Josh\n(Other possible transcriptions: my name is Ebrar)"


def test_reply_length_limit_follows_the_level(tmp_path):
    llm = FakeLLM(coach_json("Hi!"), coach_json("Hello!"))
    tutor = make_tutor(tmp_path, llm)
    tutor.start(LEARNER, Persona.FEMALE)
    Database(tmp_path / "test.db").save_level(LEARNER, "A1", 1.0, None, 0)

    tutor.start(LEARNER, Persona.FEMALE)

    assert "Reply length limit: 2 very short sentences, about 12 words" in llm.calls[1][0]


def test_guided_lesson_reaches_the_partner_and_counts_when_finished(tmp_path):
    llm = FakeLLM(coach_json("Hi!"), coach_json("Bye!", SESSION_STATE={"phase": "SESSION_END"}))
    tutor = make_tutor(tmp_path, llm)

    session_id = tutor.start(LEARNER, Persona.FEMALE, lesson="starter-1").session_id
    assert "Guided beginner conversation: Greetings" in llm.calls[0][0]
    assert tutor.suggestion(LEARNER).lesson == "starter-1"

    tutor.end(session_id)
    assert tutor.finished_count(LEARNER) == 1
    assert tutor.suggestion(LEARNER).lesson == "starter-2"


# Bugünün sohbeti Türkiye saatine göre gün içindeki konuşmalardır; dünkü konuşma gösterilmez,
# iç komutlar ve ses tanıma alternatifleri ekrana çıkmaz, açık konuşmaya devam edilebilir.
def test_today_shows_only_todays_messages_and_the_open_session(tmp_path):
    clock = FakeClock(datetime(2026, 10, 31, 20, 0, tzinfo=UTC))
    tutor = make_tutor(
        tmp_path,
        FakeLLM(
            coach_json("Good evening!"),
            coach_json("Bye!", SESSION_STATE={"phase": "SESSION_END"}),
            coach_json("Good morning!"),
            coach_json("İstanbul çok kalabalık. You can say: Istanbul is crowded."),
        ),
        clock,
    )
    yesterday = tutor.start(LEARNER, Persona.FEMALE)
    tutor.end(yesterday.session_id)

    clock.advance(hours=14)
    today = tutor.start(LEARNER, Persona.FEMALE, topic="Seyahat")
    tutor.reply(today.session_id, "İstanbul çok kalabalık", alternatives=["Istanbul"])

    chat = tutor.today(LEARNER)

    assert chat.open_session["id"] == today.session_id
    assert chat.open_session["topic"] == "Seyahat"
    assert chat.messages == [
        {"role": "assistant", "text": "Good morning!"},
        {"role": "user", "text": "İstanbul çok kalabalık"},
        {"role": "assistant", "text": "İstanbul çok kalabalık. You can say: Istanbul is crowded."},
    ]


def test_typed_messages_are_marked_and_shown_without_the_mark(tmp_path):
    llm = FakeLLM(coach_json("Hi!"), coach_json("Nice."))
    tutor = make_tutor(tmp_path, llm)
    started = tutor.start(LEARNER, Persona.FEMALE)

    tutor.reply(started.session_id, "I live in Ankara", alternatives=["Ankara"], typed=True)

    assert llm.calls[1][1][-1]["content"] == "I live in Ankara\n(Typed)"
    assert tutor.today(LEARNER).messages[1] == {"role": "user", "text": "I live in Ankara"}


# Gün içinde cevapsız kalan sorular sonraki konuşmada yeniden sorulur; ertesi gün temiz başlar.
def test_unanswered_questions_carry_over_within_the_day_only(tmp_path):
    clock = FakeClock(datetime(2026, 11, 1, 9, 0, tzinfo=UTC))
    llm = FakeLLM(
        coach_json("Hi Ebrar! Do you like cooking?"),
        coach_json("Great! What food do you like to cook?"),
        coach_json("Well done! Shall we talk again later?", SESSION_STATE={"phase": "SESSION_END"}),
        coach_json("What food do you like to cook?"),
        coach_json("Good morning, Ebrar!"),
    )
    tutor = make_tutor(tmp_path, llm, clock)
    first = tutor.start(LEARNER, Persona.FEMALE)
    tutor.reply(first.session_id, "Yes, I like it.")
    tutor.end(first.session_id)

    clock.advance(hours=2)
    tutor.start(LEARNER, Persona.FEMALE)
    later = llm.calls[3][0]
    assert "Same-day continuation: the learner" in later
    unanswered = later.split("left unanswered earlier today: ")[1].splitlines()[0]
    assert unanswered == "What food do you like to cook?"

    clock.advance(days=1)
    tutor.start(LEARNER, Persona.FEMALE)
    assert "Same-day continuation: the learner" not in llm.calls[4][0]
