# Kelime kutusunun aralıklı tekrar takvimi: dokümandaki 1-3-7-14-30 gün kuralı.
from datetime import date, timedelta

INTERVALS = [1, 3, 7, 14, 30]
MASTERED_AFTER = len(INTERVALS)


# Tekrar sayısına göre öğrenme durumu.
def status_for(review_count: int) -> str:
    if review_count == 0:
        return "NEW"
    if review_count < 3:
        return "LEARNING"
    if review_count < MASTERED_AFTER:
        return "REVIEW"
    return "MASTERED"


# Bir sonraki tekrar tarihi: kaç kez başarıyla tekrar edildiyse o kadar uzun aralık.
def next_review(review_count: int, today: date) -> date:
    interval = INTERVALS[min(review_count, len(INTERVALS) - 1)]
    return today + timedelta(days=interval)


# Boşluğu ("...") olan ifadeler kalıptır ("I'm looking forward to ..."); diğerleri kelimedir.
def kind(expression: str) -> str:
    return "pattern" if "..." in expression or "…" in expression else "word"


# Kelime kutusuna yalnızca kelime ve kalıp girer. Nokta, soru ya da ünlem işaretiyle biten ve
# "..." boşluğu olmayan çok kelimeli bir ifade tam cümle sayılır ("I'm from Turkey.").
def is_sentence(expression: str) -> bool:
    text = expression.strip()
    if kind(text) == "pattern":
        return False
    return len(text.split()) > 1 and text[-1:] in ".?!"
