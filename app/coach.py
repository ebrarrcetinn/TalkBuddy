# Koçun beyni: talimatı hazırlar, Claude'a sorar, cevabı doğrular ve sohbet geçmişini tutar.
import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from app.llm import LLMClient
from app.schemas import CoachResponse, Persona

PROMPT_PATH = Path(__file__).parent / "prompts" / "coach_system.md"

# Kullanıcı mesajı olmayan anlarda Claude'a gönderilen iç komutlar.
SESSION_START = "[Session started. Greet the learner and begin.]"
SESSION_END = "[The learner wants to end the session. Give the session summary.]"


# Dökümdeki bir kelimeye dokunulunca istenen kısa açıklama.
EXPLAIN_PROMPT = (
    "You help Turkish speakers learning English. Explain one English word, phrase or sentence "
    'pattern ("..." marks the open slot of a pattern) as it is used in the given sentence. '
    "Reply with JSON only, no other text:\n"
    '{"turkish_meaning": "<short Turkish meaning; for a pattern, its Turkish equivalent>", '
    '"example": "<one short, simple English example sentence using it in the same meaning>"}'
)


class WordExplanation(BaseModel):
    turkish_meaning: str = Field(min_length=1)
    example: str = ""


# Claude'un cevabı iki denemede de geçerli JSON olmazsa fırlatılır.
class CoachOutputError(Exception):
    pass


# Tek bir sohbet oturumu: seçilen koç, o ana kadarki mesajlar ve öğrencinin kayıtlı profili.
@dataclass
class Session:
    persona: Persona
    history: list[dict[str, str]] = field(default_factory=list)
    learner_context: str = "Learner profile: new learner, no saved records."


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


# Talimatın sonuna oturuma özel bilgileri ekler (dokümandaki "SESSION CONTEXT").
def build_context(session: Session) -> str:
    return (
        f"\n## SESSION CONTEXT\n\nSelected persona: {session.persona}\n{session.learner_context}\n"
    )


# Cevabın içindeki JSON'u bulur ve şemaya göre doğrular.
# Claude JSON'un etrafına metin ya da ``` işaretleri eklese bile ilk { ile son } arası alınır.
def parse_response(raw: str) -> CoachResponse:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise CoachOutputError("No JSON object in model output")
    try:
        return CoachResponse.model_validate(json.loads(raw[start : end + 1]))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise CoachOutputError(str(exc)) from exc


class Coach:
    # Talimat dosyası bir kez okunur; bozuk cevapta en fazla max_attempts kez sorulur.
    def __init__(self, llm: LLMClient, max_attempts: int = 2):
        self._llm = llm
        self._system = load_system_prompt()
        self._max_attempts = max_attempts

    def start(self, session: Session) -> CoachResponse:
        return self._turn(session, SESSION_START)

    def reply(self, session: Session, text: str) -> CoachResponse:
        return self._turn(session, text)

    def end(self, session: Session) -> CoachResponse:
        return self._turn(session, SESSION_END)

    def explain(self, word: str, sentence: str) -> WordExplanation:
        content = f"Word: {word}\nSentence: {sentence or word}"
        last_error: Exception | None = None
        for _ in range(self._max_attempts):
            raw = self._llm.complete(EXPLAIN_PROMPT, [{"role": "user", "content": content}])
            start, end = raw.find("{"), raw.rfind("}")
            try:
                return WordExplanation.model_validate(json.loads(raw[start : end + 1]))
            except (ValueError, ValidationError) as exc:
                last_error = exc
        raise CoachOutputError("Invalid word explanation") from last_error

    # Bir tur: mesajı ekle → Claude'a sor → doğrula → geçerliyse geçmişe kaydet.
    def _turn(self, session: Session, user_text: str) -> CoachResponse:
        messages = [*session.history, {"role": "user", "content": user_text}]
        context = build_context(session)

        last_error: CoachOutputError | None = None
        for _ in range(self._max_attempts):
            raw = self._llm.complete(self._system, messages, context)
            try:
                response = parse_response(raw)
                break
            except CoachOutputError as exc:
                last_error = exc
        else:
            raise last_error

        # Geçmiş yalnızca başarılı turda güncellenir; bozuk tur sohbeti bozmaz.
        session.history = [*messages, {"role": "assistant", "content": raw}]
        return response
