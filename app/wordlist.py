# Oxford 5000 kelime listesi (A1–C1): değerlendirme havuzu ve konuşmadaki kelime seviyesi.
# Liste Oxford University Press'e ait olduğu için depoya eklenmez; PDF'ten üretilir.
import csv
from dataclasses import dataclass
from pathlib import Path

WORDLIST_PATH = Path(__file__).parent.parent / "data" / "oxford5000.csv"


@dataclass(frozen=True)
class Entry:
    word: str
    pos: str
    level: str


# Dosya yoksa boş liste döner; uygulama değerlendirme olmadan çalışmaya devam eder.
def load(path: Path = WORDLIST_PATH) -> list[Entry]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as file:
        return [Entry(row["word"], row["pos"], row["level"]) for row in csv.DictReader(file)]


def save(entries: list[Entry], path: Path = WORDLIST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["word", "pos", "level"])
        writer.writerows((entry.word, entry.pos, entry.level) for entry in entries)
