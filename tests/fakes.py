# Testlerde gerçek Claude yerine kullanılan yardımcılar.
import json
import random
from datetime import UTC, datetime, timedelta

from app import assessment
from app.accounts import Accounts
from app.coach import Coach
from app.db import Database
from app.level import LexicalProfile
from app.tutor import Tutor
from app.wordlist import Entry


# Koçun JSON cevabını üretir; testler sadece değiştirmek istedikleri alanları verir.
def coach_json(spoken: str = "Hello! Do you know what 'happy' means?", **overrides) -> str:
    payload = {
        "ACTIVE_PERSONA": "Female_Coach",
        "SPOKEN_TEXT": spoken,
        "VOCAB_BOX_UPDATE": [],
        "ERROR_TRACKING": {
            "latest_error": None,
            "corrected_version": None,
            "focus_area": None,
            "repeated_errors": [],
        },
        "CURRENT_LEVEL": "Undetermined",
        "SESSION_STATE": {
            "phase": "VOCABULARY_ASSESSMENT",
            "current_topic": "Vocabulary",
            "awaiting_repetition": False,
        },
        "MEMORY_UPDATE": {
            "new_vocabulary": [],
            "reviewed_vocabulary": [],
            "grammar_weaknesses": [],
            "mastered_structures": [],
            "last_topic": "Vocabulary Assessment",
            "next_focus": None,
            "session_summary": None,
        },
    }
    payload.update(overrides)
    return json.dumps(payload)


# LLMClient sözleşmesine uyan sahte LLM: verilen cevapları sırayla döndürür
# ve kendisine gönderilen her isteği kaydeder.
class FakeLLM:
    def __init__(self, *outputs: str):
        self.outputs = list(outputs)
        self.calls: list[tuple[str, list[dict[str, str]]]] = []

    def complete(self, system: str, messages: list[dict[str, str]], context: str = "") -> str:
        self.calls.append((system + context, messages))
        return self.outputs.pop(0)


# Testlerde zamanı elle ilerletebildiğimiz saat.
class FakeClock:
    def __init__(self, start: datetime = datetime(2026, 11, 1, 10, 0, tzinfo=UTC)):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


def make_tutor(tmp_path, llm: FakeLLM, clock: FakeClock | None = None, plan=None) -> Tutor:
    lexicon = LexicalProfile({"happy": "A1", "school": "A1", "go": "A1", "ambiguous": "C1"})
    return Tutor(
        Coach(llm),
        Database(tmp_path / "test.db"),
        lexicon,
        clock or FakeClock(),
        plan,
        random.Random(3),
    )


# Gönderilen e-postaları gerçekten göndermek yerine listede tutar.
class FakeMailer:
    def __init__(self):
        self.sent: list[tuple[str, str, str]] = []

    def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))


# Testlerde gerçek Oxford listesi yerine her seviyeden yeterli sayıda uydurma kelime kullanılır.
LEVEL_NAMES = {"A1": "alpha", "A2": "bravo", "B1": "charlie", "B2": "delta", "C1": "echo"}


def fake_entries() -> list[Entry]:
    letters = "abcdefghijklmnopqrst"
    return [
        Entry(f"{name}{pos}{letter}", pos, level)
        for level, name in LEVEL_NAMES.items()
        for pos in ("noun", "verb", "adjective", "adverb")
        for letter in letters
    ]


def make_accounts(
    tmp_path,
    mailer: FakeMailer | None = None,
    clock: FakeClock | None = None,
    pool: dict[str, list[Entry]] | None = None,
):
    return Accounts(
        Database(tmp_path / "test.db"),
        mailer or FakeMailer(),
        "http://localhost:8080",
        clock or FakeClock(),
        random.Random(7),
        assessment.build_pool(fake_entries()) if pool is None else pool,
    )
