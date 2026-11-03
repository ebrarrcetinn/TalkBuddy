# Başlangıç rotası ve günün önerilen konuşması.
# A1–A2 kullanıcıları kısa, kolay ve sıralı konuşmalarla başlar; B1 ve üzeri rotaya zorlanmaz,
# onlara ilgi alanlarından bir konu önerilir. Herkes istediği an serbest konuşmaya geçebilir.
from dataclasses import dataclass

BEGINNER_LEVELS = {None, "A1", "A2"}


@dataclass(frozen=True)
class Lesson:
    key: str
    title: str
    description: str
    focus: str


STARTER_PATH = [
    Lesson(
        "starter-1",
        "Tanışalım",
        "Selamlaşma, adın, nereli olduğun ve nasıl olduğun.",
        "Greetings, saying your name, where you are from and how you are.",
    ),
    Lesson(
        "starter-2",
        "Günüm",
        "Sabah kalkınca neler yaptığın, okul ya da iş.",
        "Daily routine in the present simple: wake up, breakfast, work or school.",
    ),
    Lesson(
        "starter-3",
        "Sevdiğim şeyler",
        "Sevdiğin yemekler, hobiler ve boş zaman.",
        "Likes and dislikes with 'I like' and 'I don't like': food, hobbies, free time.",
    ),
    Lesson(
        "starter-4",
        "Ailem ve arkadaşlarım",
        "Ailen ve arkadaşların hakkında kısa cümleler.",
        "Family and friends: 'I have', 'he is', simple descriptions.",
    ),
    Lesson(
        "starter-5",
        "Kafede",
        "Bir kafede sipariş vermek ve fiyat sormak.",
        "Role-play ordering at a café: 'Can I have...', 'How much is...'.",
    ),
    Lesson(
        "starter-6",
        "Hafta sonum",
        "Geçen hafta sonu ne yaptığını anlatmak.",
        "Talking about last weekend with a few common past simple verbs.",
    ),
    Lesson(
        "starter-7",
        "Şehrim",
        "Yaşadığın yer, sevdiğin mekânlar, yol tarifi.",
        "Your town: places, 'there is / there are', simple directions.",
    ),
    Lesson(
        "starter-8",
        "Planlarım",
        "Bu hafta ve yakın gelecek için planların.",
        "Near-future plans with 'I'm going to'.",
    ),
]
LESSONS = {lesson.key: lesson for lesson in STARTER_PATH}


@dataclass(frozen=True)
class Suggestion:
    kind: str  # "lesson" (başlangıç rotası), "topic" (ilgi alanı) ya da "free" (serbest konuşma)
    title: str
    description: str
    minutes: int
    lesson: str | None = None
    topic: str | None = None
    step: int | None = None
    total_steps: int | None = None


def starter_minutes(level: str | None) -> int:
    return 5 if level in (None, "A1") else 10


# Başlangıç seviyesinde rotanın tamamlanmamış ilk adımı; diğer seviyelerde ilgi alanları sırayla.
def suggest(
    level: str | None,
    finished_lessons: set[str],
    interests: list[str],
    last_topic: str | None,
) -> Suggestion:
    if level in BEGINNER_LEVELS:
        for step, lesson in enumerate(STARTER_PATH, start=1):
            if lesson.key not in finished_lessons:
                return Suggestion(
                    "lesson",
                    lesson.title,
                    lesson.description,
                    starter_minutes(level),
                    lesson=lesson.key,
                    step=step,
                    total_steps=len(STARTER_PATH),
                )
    if interests:
        index = interests.index(last_topic) + 1 if last_topic in interests else 0
        topic = interests[index % len(interests)]
        return Suggestion(
            "topic", topic, "İlgi alanlarından biri hakkında sohbet.", 10, topic=topic
        )
    return Suggestion("free", "Serbest konuşma", "Partnerin bugün sana uygun bir konu açar.", 10)
