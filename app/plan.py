# Seviye öğrenme planı: her seviyenin Oxford kelimeleri. Plan ilerlemesi ve günün yeni kelimeleri
# buradan hesaplanır. Değerlendirme kelimeleri planın tamamı sayılmaz; yalnızca öncelik belirler.
import random
from dataclasses import dataclass

from app import assessment
from app.wordlist import Entry


@dataclass(frozen=True)
class PlanProgress:
    level: str
    total: int
    known: int
    learning: int

    @property
    def percent(self) -> int:
        return self.known * 100 // self.total if self.total else 0


class LearningPlan:
    def __init__(self, entries: list[Entry]):
        pool = assessment.build_pool(entries)
        self._words = {
            level: [entry.word.lower() for entry in words] for level, words in pool.items()
        }

    def words(self, level: str | None) -> list[str]:
        return self._words.get(level or "", [])

    # Bilinen: kullanabildiği (MASTERED) ya da değerlendirmede işaretlediği kelimeler.
    def progress(
        self, level: str | None, known: set[str], learning: set[str]
    ) -> PlanProgress | None:
        words = set(self.words(level))
        if not words:
            return None
        known_here = words & known
        learning_here = (words & learning) - known_here
        return PlanProgress(level, len(words), len(known_here), len(learning_here))

    # Günün yeni kelimeleri: önce değerlendirmede gösterilip işaretlenmeyenler, sonra planın kalanı.
    def suggest(
        self,
        level: str | None,
        exclude: set[str],
        prefer: set[str],
        count: int,
        rng: random.Random,
    ) -> list[str]:
        candidates = [word for word in self.words(level) if word not in exclude]
        first = [word for word in candidates if word in prefer]
        rest = [word for word in candidates if word not in prefer]
        rng.shuffle(first)
        rng.shuffle(rest)
        return (first + rest)[:count]
