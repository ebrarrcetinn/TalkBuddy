# Koçun talimatı hazırlamasını, cevabı doğrulamasını ve sohbet geçmişini test eder.
import json

import pytest

from app.coach import SESSION_START, Coach, CoachOutputError, Session, parse_response
from app.schemas import Persona
from tests.fakes import FakeLLM, coach_json

# Cevaptan JSON çıkarma ve doğrulama


def test_parse_response_reads_valid_json():
    response = parse_response(coach_json("Hi there!"))

    assert response.spoken_text == "Hi there!"
    assert response.active_persona == "Female_Coach"
    assert response.session_state.awaiting_repetition is False


def test_parse_response_ignores_text_around_json():
    response = parse_response("Here you go:\n```json\n" + coach_json() + "\n```")

    assert response.current_level == "Undetermined"


def test_parse_response_fills_missing_fields_with_defaults():
    raw = json.dumps({"ACTIVE_PERSONA": "Male_Coach", "SPOKEN_TEXT": "Hi!"})

    response = parse_response(raw)

    assert response.current_level == "Undetermined"
    assert response.vocab_box_update == []


def test_expression_defaults_to_neutral():
    assert parse_response(coach_json()).expression == "neutral"


def test_expression_is_read_and_unknown_values_fall_back():
    assert parse_response(coach_json(EXPRESSION="Laugh")).expression == "laugh"
    assert parse_response(coach_json(EXPRESSION="surprised")).expression == "neutral"


def test_parse_response_accepts_plain_string_vocab():
    response = parse_response(coach_json(VOCAB_BOX_UPDATE=["borrow"]))

    assert response.vocab_box_update[0].expression == "borrow"


@pytest.mark.parametrize(
    "raw",
    [
        "Sorry, I cannot help.",
        "{broken json",
        json.dumps({"ACTIVE_PERSONA": "Robot", "SPOKEN_TEXT": "Hi"}),
        json.dumps({"ACTIVE_PERSONA": "Female_Coach", "SPOKEN_TEXT": ""}),
    ],
)
def test_parse_response_rejects_invalid_output(raw):
    with pytest.raises(CoachOutputError):
        parse_response(raw)


# Bir turun akışı


def test_start_sends_prompt_and_persona():
    llm = FakeLLM(coach_json())

    Coach(llm).start(Session(persona=Persona.MALE))

    system, messages = llm.calls[0]
    assert system.startswith("# MASTER SYSTEM PROMPT")
    assert "Selected persona: Male_Coach" in system
    assert messages == [{"role": "user", "content": SESSION_START}]


def test_reply_keeps_conversation_history():
    llm = FakeLLM(coach_json("Welcome!"), coach_json("Nice answer."))
    coach = Coach(llm)
    session = Session(persona=Persona.FEMALE)

    coach.start(session)
    response = coach.reply(session, "It means feeling good.")

    assert response.spoken_text == "Nice answer."
    assert [m["role"] for m in session.history] == ["user", "assistant", "user", "assistant"]
    assert llm.calls[1][1][-1] == {"role": "user", "content": "It means feeling good."}


def test_invalid_output_is_retried_once():
    llm = FakeLLM("not json", coach_json("Recovered."))
    session = Session(persona=Persona.FEMALE)

    response = Coach(llm).start(session)

    assert response.spoken_text == "Recovered."
    assert len(llm.calls) == 2
    assert len(session.history) == 2


def test_failed_turn_leaves_history_unchanged():
    llm = FakeLLM("not json", "still not json")
    session = Session(persona=Persona.FEMALE)

    with pytest.raises(CoachOutputError):
        Coach(llm).start(session)

    assert session.history == []


# Değişmeyen talimat ile her mesajda değişen oturum bilgisi ayrı gider; talimat önbelleğe
# alınabilsin diye her turda birebir aynı kalmalıdır.
class SplitLLM:
    def __init__(self):
        self.calls = []

    def complete(self, system, messages, context=""):
        self.calls.append((system, context))
        return coach_json()


def test_instructions_stay_identical_across_turns_and_context_is_separate():
    llm = SplitLLM()
    coach = Coach(llm)
    session = Session(persona=Persona.FEMALE, learner_context="Time used: 1 minute.")

    coach.start(session)
    session.learner_context = "Time used: 2 minutes."
    coach.reply(session, "Hello")

    (first_system, first_context), (second_system, second_context) = llm.calls
    assert first_system == second_system
    assert "Time used" not in first_system
    assert "1 minute" in first_context and "2 minutes" in second_context


def test_prompt_tells_the_partner_how_to_answer_turkish_turns():
    llm = FakeLLM(coach_json())

    Coach(llm).start(Session(persona=Persona.FEMALE))

    system = llm.calls[0][0]
    assert "### SPEAKING TURKISH DURING THE CONVERSATION" in system
    assert "Bunu nasıl söylerim?" in system
    assert "Keep the JSON short" in system


def test_prompt_saves_what_the_learner_does_not_know():
    llm = FakeLLM(coach_json())

    Coach(llm).start(Session(persona=Persona.FEMALE))

    system = llm.calls[0][0]
    assert "Bu kelimeyi bilmiyorum." in system
    assert "Bu kalıbı bilmiyorum." in system


def test_prompt_answers_the_learners_question_first():
    llm = FakeLLM(coach_json())

    Coach(llm).start(Session(persona=Persona.FEMALE))

    assert "### THE LEARNER'S QUESTION COMES FIRST" in llm.calls[0][0]
    assert "Doğru mu söyledim?" in llm.calls[0][0]
