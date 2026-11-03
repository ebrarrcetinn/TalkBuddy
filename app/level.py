# Seviye motoru: Claude'un tahminini kelime seviyesiyle birleştirir ve seviyenin zıplamasını önler.
import re
from dataclasses import dataclass

from app import wordlist

LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]

# Claude'un tahmini ana sinyal, kelime seviyesi destekleyici sinyal.
CLAUDE_WEIGHT = 0.7
# Her yeni gözlem, birikmiş skoru bu oranda kendine çeker.
SMOOTHING = 0.35
# Seviye değişmeden önce skorun sınırı ne kadar aşması gerektiği.
MARGIN = 0.25
# Yeni seviyenin kabul edilmesi için üst üste kaç turda görülmesi gerektiği.
CONFIRM_TURNS = 2
# Kelime seviyesi hesaplamak için gereken en az farklı kelime sayısı.
MIN_WORDS = 5


def to_score(level: str | None) -> float | None:
    if level is None:
        return None
    level = level.strip().upper()
    return float(LEVELS.index(level) + 1) if level in LEVELS else None


def to_level(score: float) -> str:
    return LEVELS[min(max(round(score), 1), len(LEVELS)) - 1]


# Öğrencinin seviye durumu: birikmiş skor, gösterilen seviye ve onay bekleyen aday seviye.
@dataclass(frozen=True)
class LevelState:
    score: float | None = None
    level: str | None = None
    pending: str | None = None
    pending_turns: int = 0


def update(state: LevelState, claude_level: str | None, lexical: float | None) -> LevelState:
    observed = to_score(claude_level)
    if observed is None:
        return state
    if lexical is not None:
        observed = CLAUDE_WEIGHT * observed + (1 - CLAUDE_WEIGHT) * lexical

    # İlk tahmin doğrudan kabul edilir.
    if state.score is None or state.level is None:
        return LevelState(score=observed, level=to_level(observed))

    score = state.score + SMOOTHING * (observed - state.score)
    current = to_score(state.level)
    if abs(score - current) < 0.5 + MARGIN:
        return LevelState(score=score, level=state.level)

    # Aday seviye ancak CONFIRM_TURNS tur üst üste görülürse kabul edilir.
    candidate = to_level(score)
    turns = state.pending_turns + 1 if candidate == state.pending else 1
    if turns >= CONFIRM_TURNS:
        return LevelState(score=score, level=candidate)
    return LevelState(score=score, level=state.level, pending=candidate, pending_turns=turns)


# Kelimelerin CEFR seviyeleri (Oxford 5000); birden çok seviyesi olan kelimede en düşüğü alınır.
class LexicalProfile:
    def __init__(self, words: dict[str, str]):
        self._words = words

    @classmethod
    def from_entries(cls, entries: list[wordlist.Entry]) -> "LexicalProfile":
        words: dict[str, str] = {}
        for entry in entries:
            word = entry.word.lower()
            known = words.get(word)
            if known is None or to_score(entry.level) < to_score(known):
                words[word] = entry.level
        return cls(words)

    # Basit kök bulma: kelimenin kendisi yoksa yaygın ekleri atarak dener.
    def level_of(self, word: str) -> str | None:
        candidates = [word]
        for suffix, replacement in (
            ("ies", "y"),
            ("es", ""),
            ("s", ""),
            ("ed", ""),
            ("ed", "e"),
            ("ing", ""),
            ("ing", "e"),
            ("er", ""),
            ("est", ""),
        ):
            if word.endswith(suffix) and len(word) > len(suffix) + 2:
                candidates.append(word[: -len(suffix)] + replacement)
        for candidate in candidates:
            if candidate in self._words:
                return self._words[candidate]
        return None

    # Mesajdaki en ileri seviyeli üç kelimenin ortalaması; yeterli kelime yoksa None.
    def score(self, text: str) -> float | None:
        words = set(re.findall(r"[a-z]+(?:'[a-z]+)?", text.lower()))
        scores = sorted(
            (to_score(level) for word in words if (level := self.level_of(word))), reverse=True
        )
        if len(scores) < MIN_WORDS:
            return None
        top = scores[:3]
        return sum(top) / len(top)
