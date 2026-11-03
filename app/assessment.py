# Başlangıç kelime değerlendirmesi: her seviyeden 30 kelime, işaretlenen sayıya göre seviye önerisi.
import random
from dataclasses import dataclass

from app.wordlist import Entry

# Oxford 5000 C2 içermediği için değerlendirme A1–C1 arası beş bölümdür.
LEVELS = ["A1", "A2", "B1", "B2", "C1"]

SECTION_SIZE = 30
# Eşik yüzde 95: 29/30 geçer, 28/30 geçmez. Oran yuvarlanmadan karşılaştırılır.
PASS_RATIO = 0.95
# Sözcük türleri dengeli dağılsın diye her bölümdeki hedef sayılar.
POS_QUOTA = {"noun": 12, "verb": 8, "adjective": 6, "adverb": 4}


# Havuz: yalnızca tek kelimelik isim, fiil, sıfat ve zarflar. Kelime, listedeki en düşük
# seviyesinde (hangi türde olursa olsun) yer alır; üst seviyede başka anlamıyla tekrar sorulmaz.
def build_pool(entries: list[Entry]) -> dict[str, list[Entry]]:
    lowest: dict[str, int] = {}
    for entry in entries:
        if entry.level in LEVELS:
            rank = LEVELS.index(entry.level)
            lowest[entry.word] = min(rank, lowest.get(entry.word, rank))

    chosen: dict[str, Entry] = {}
    for entry in entries:
        if entry.pos not in POS_QUOTA or entry.level not in LEVELS:
            continue
        if not entry.word.isalpha() or len(entry.word) < 3:
            continue
        if LEVELS.index(entry.level) == lowest[entry.word]:
            chosen.setdefault(entry.word, entry)

    pool: dict[str, list[Entry]] = {level: [] for level in LEVELS}
    for entry in sorted(chosen.values(), key=lambda item: item.word):
        pool[entry.level].append(entry)
    return pool


def is_ready(pool: dict[str, list[Entry]]) -> bool:
    return all(len(pool.get(level, [])) >= SECTION_SIZE for level in LEVELS)


# Her seviye için ayrı bir bölüm: türlere göre seçilir, sonra karışık sıralanır.
def build_sections(pool: dict[str, list[Entry]], rng: random.Random) -> list[list[str]]:
    sections = []
    for level in LEVELS:
        words = pool[level]
        chosen: list[Entry] = []
        for pos, quota in POS_QUOTA.items():
            candidates = [word for word in words if word.pos == pos]
            chosen += rng.sample(candidates, min(quota, len(candidates)))
        remaining = [word for word in words if word not in chosen]
        chosen += rng.sample(remaining, SECTION_SIZE - len(chosen))
        rng.shuffle(chosen)
        sections.append([word.word for word in chosen])
    return sections


@dataclass(frozen=True)
class LevelScore:
    level: str
    selected: int
    total: int
    passed: bool


@dataclass(frozen=True)
class AssessmentResult:
    scores: list[LevelScore]
    recommended_level: str
    inconsistent: bool


def passes(selected: int, total: int = SECTION_SIZE) -> bool:
    return selected / total >= PASS_RATIO


def evaluate(selections: list[list[str]]) -> AssessmentResult:
    scores = [
        LevelScore(level, len(words), SECTION_SIZE, passes(len(words)))
        for level, words in zip(LEVELS, selections, strict=True)
    ]

    # A1'den başlayarak aralıksız geçilen en yüksek seviye önerilir; A1 geçilemezse A1.
    recommended = "A1"
    for score in scores:
        if not score.passed:
            break
        recommended = score.level

    # Geçilemeyen bir seviyenin üstünde geçilen seviye varsa dağılım tutarsızdır.
    first_fail = next((i for i, score in enumerate(scores) if not score.passed), len(scores))
    inconsistent = any(score.passed for score in scores[first_fail + 1 :])
    return AssessmentResult(scores, recommended, inconsistent)
