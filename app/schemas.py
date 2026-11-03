# Koçun JSON cevabının şeması: Claude'dan gelen her cevap buna göre doğrulanır.
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


# Seçilebilecek koçlar; bunların dışındaki değerler reddedilir.
class Persona(StrEnum):
    FEMALE = "Female_Coach"
    MALE = "Male_Coach"


# Oturumun aşamaları: önce seviye testi, sonra pratik.
class Phase(StrEnum):
    VOCABULARY_ASSESSMENT = "VOCABULARY_ASSESSMENT"
    CONVERSATION_ASSESSMENT = "CONVERSATION_ASSESSMENT"
    PRACTICE = "PRACTICE"
    SESSION_END = "SESSION_END"


# Karikatür koçun yüz ifadesi: ekrandaki çizimi ve kahkaha sesini belirler.
class Expression(StrEnum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    LAUGH = "laugh"


# Öğrenci "daha yavaş konuş" gibi bir istekte bulunursa konuşma hızının nasıl değişeceği.
class SpeechRate(StrEnum):
    SLOWER = "slower"
    FASTER = "faster"


# Kelime kutusuna eklenecek tek bir öğe; sadece ifadenin kendisi zorunlu.
class VocabEntry(BaseModel):
    expression: str
    turkish_meaning: str | None = None
    cefr_level: str | None = None
    example: str | None = None


# Son hata, doğru hâli ve tekrar eden hatalar.
class ErrorTracking(BaseModel):
    latest_error: str | None = None
    corrected_version: str | None = None
    focus_area: str | None = None
    repeated_errors: list[str] = Field(default_factory=list)


# Oturumun anlık durumu; awaiting_repetition true ise koç tekrar bekliyor.
class SessionState(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    phase: Phase = Phase.VOCABULARY_ASSESSMENT
    current_topic: str | None = None
    awaiting_repetition: bool = False


# Bu turda hafızaya kaydedilecek öğrenme değişiklikleri.
class MemoryUpdate(BaseModel):
    new_vocabulary: list[str] = Field(default_factory=list)
    reviewed_vocabulary: list[str] = Field(default_factory=list)
    grammar_weaknesses: list[str] = Field(default_factory=list)
    mastered_structures: list[str] = Field(default_factory=list)
    last_topic: str | None = None
    next_focus: str | None = None
    session_summary: str | None = None


# Cevabın tamamı. JSON'daki büyük harfli adlar alias ile Python adlarına eşlenir.
# Sadece ACTIVE_PERSONA ve SPOKEN_TEXT zorunlu; eksik alanlar varsayılan değer alır.
class CoachResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    active_persona: Persona = Field(alias="ACTIVE_PERSONA")
    spoken_text: str = Field(alias="SPOKEN_TEXT", min_length=1)
    vocab_box_update: list[VocabEntry] = Field(alias="VOCAB_BOX_UPDATE", default_factory=list)
    error_tracking: ErrorTracking = Field(alias="ERROR_TRACKING", default_factory=ErrorTracking)
    current_level: str = Field(alias="CURRENT_LEVEL", default="Undetermined")
    session_state: SessionState = Field(alias="SESSION_STATE", default_factory=SessionState)
    memory_update: MemoryUpdate = Field(alias="MEMORY_UPDATE", default_factory=MemoryUpdate)
    expression: Expression = Field(alias="EXPRESSION", default=Expression.NEUTRAL)
    speech_rate: SpeechRate | None = Field(alias="SPEECH_RATE", default=None)

    # Claude kelimeyi düz metin yazarsa ("borrow") nesneye çevirir; istenen kelime kaybolmaz.
    @field_validator("vocab_box_update", mode="before")
    @classmethod
    def _accept_plain_strings(cls, value):
        if isinstance(value, list):
            return [{"expression": v} if isinstance(v, str) else v for v in value]
        return value

    # Tanınmayan bir ifade gelirse cevap reddedilmez, nötr kabul edilir.
    @field_validator("expression", mode="before")
    @classmethod
    def _default_unknown_expression(cls, value):
        value = str(value).strip().lower()
        return value if value in {item.value for item in Expression} else Expression.NEUTRAL

    # Hız isteği yoksa ya da tanınmıyorsa değişiklik yapılmaz.
    @field_validator("speech_rate", mode="before")
    @classmethod
    def _ignore_unknown_rate(cls, value):
        if value is None:
            return None
        value = str(value).strip().lower()
        return value if value in {item.value for item in SpeechRate} else None
