# Gelişim, seri, günlük hedef, rozetler ve bildirimler. Hepsi kayıtlı konuşmalardan ve kelimelerden
# hesaplanır; gerçek veriden çıkmayan hiçbir puan üretilmez.
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from math import ceil

from app.path import LESSONS, STARTER_PATH

# Kullanıcılar Türkiye'de; Türkiye 2016'dan beri yaz saati uygulamadığı için sabit UTC+3 yeterli.
LOCAL_TIME = timezone(timedelta(hours=3))
DAY_NAMES = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
DAILY_GOALS = [5, 10, 15, 20]
DEFAULT_DAILY_GOAL = 10
NOTIFICATION_TYPES = ["daily", "review", "weekly", "badge", "monthly"]


def local_day(timestamp: str) -> date:
    return datetime.fromisoformat(timestamp).astimezone(LOCAL_TIME).date()


def session_minutes(session) -> int:
    started = datetime.fromisoformat(session["started_at"])
    ended = datetime.fromisoformat(session["ended_at"])
    return max(1, ceil((ended - started).total_seconds() / 60))


# Konuşulan günlerden seri: bugün ya da dün konuşulduysa seri sürüyor sayılır.
def current_streak(days: set[date], today: date) -> int:
    day = today if today in days else today - timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def best_streak(days: set[date]) -> int:
    best = 0
    for day in days:
        if day - timedelta(days=1) in days:
            continue
        length = 0
        while day + timedelta(days=length) in days:
            length += 1
        best = max(best, length)
    return best


@dataclass(frozen=True)
class Badge:
    key: str
    title: str
    description: str


BADGES = [
    Badge("first-talk", "İlk konuşma", "İlk konuşmanı tamamladın."),
    Badge("streak-3", "3 gün üst üste", "Üç gün arka arkaya konuştun."),
    Badge("streak-7", "Bir hafta", "Yedi gün arka arkaya konuştun."),
    Badge("words-10", "10 kelime", "Kelime listende 10 kelime var."),
    Badge("words-50", "50 kelime", "Kelime listende 50 kelime var."),
    Badge("minutes-60", "Bir saat", "Toplam 60 dakika konuştun."),
    Badge("starter-path", "Başlangıç rotası", "Başlangıç rotasının bütün adımlarını bitirdin."),
    Badge("monthly-review", "Aylık değerlendirme", "İlk aylık konuşma değerlendirmeni yaptın."),
]


@dataclass
class Progress:
    today_minutes: int
    daily_goal: int
    streak: int
    best_streak: int
    total_minutes: int
    sessions: int
    week: list[dict]
    words_total: int
    words_mastered: int
    words_learning: int
    words_due: int
    reviews_done: int
    mistakes: list[dict]
    topics: list[str]
    monthly_reviews: list[dict]
    earned_badges: set[str] = field(default_factory=set)
    advice: list[str] = field(default_factory=list)

    @property
    def goal_met(self) -> bool:
        return self.today_minutes >= self.daily_goal


def build(sessions, words, weaknesses, daily_goal: int, now: datetime) -> Progress:
    today = now.astimezone(LOCAL_TIME).date()
    minutes_by_day: dict[date, int] = {}
    for session in sessions:
        day = local_day(session["ended_at"])
        minutes_by_day[day] = minutes_by_day.get(day, 0) + session_minutes(session)
    days = set(minutes_by_day)

    week = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        week.append(
            {
                "day": DAY_NAMES[day.weekday()],
                "date": day.isoformat(),
                "minutes": minutes_by_day.get(day, 0),
            }
        )

    topics = []
    for session in sessions:
        name = (
            LESSONS[session["lesson"]].title if session["lesson"] in LESSONS else session["topic"]
        )
        if name and name not in topics:
            topics.append(name)

    monthly = [
        {"date": local_day(s["ended_at"]).isoformat(), "summary": s["summary"] or ""}
        for s in sessions
        if s["mode"] == "monthly"
    ]
    mastered = sum(1 for word in words if word["status"] == "MASTERED")
    # Tekrar zamanı: kelime defterindeki kuralla aynı (bugün ya da önceki bir güne planlanmış).
    due = sum(
        1
        for word in words
        if word["status"] != "MASTERED" and word["next_review"][:10] <= now.date().isoformat()
    )
    progress = Progress(
        today_minutes=minutes_by_day.get(today, 0),
        daily_goal=daily_goal,
        streak=current_streak(days, today),
        best_streak=best_streak(days),
        total_minutes=sum(minutes_by_day.values()),
        sessions=len(sessions),
        week=week,
        words_total=len(words),
        words_mastered=mastered,
        words_learning=len(words) - mastered,
        words_due=due,
        reviews_done=sum(word["review_count"] for word in words),
        mistakes=[{"name": row["name"], "count": row["count"]} for row in weaknesses],
        topics=topics,
        monthly_reviews=monthly,
    )
    progress.earned_badges = earned(progress, {s["lesson"] for s in sessions})
    progress.advice = advice(progress)
    return progress


# Kişisel öneriler: yalnızca kayıtlarda gerçekten görülen durumlardan, en fazla üç tane.
def advice(progress: Progress) -> list[str]:
    if not progress.sessions:
        return []
    items = []
    if progress.mistakes:
        top = progress.mistakes[0]["name"]
        items.append(
            f"En sık düzeltilen yapın: {top}. Konuşurken bu yapıyı bilerek kullanmayı dene."
        )
    if progress.words_due:
        items.append(
            f"{progress.words_due} kelimenin tekrar zamanı geldi. Kelimelerim'den dinleyip "
            "bir sonraki konuşmada kullanabilirsin."
        )
    if not progress.goal_met:
        left = progress.daily_goal - progress.today_minutes
        items.append(f"Bugünkü hedefine {left} dakika kaldı; kısa bir konuşma yeter.")
    active_days = sum(1 for day in progress.week if day["minutes"])
    if active_days < 3:
        items.append(
            "Son 7 günde "
            f"{active_days} gün konuştun. Uzun tek bir konuşma yerine her gün birkaç dakika "
            "konuşmak daha kalıcı olur."
        )
    return items[:3]


def earned(progress: Progress, finished_lessons: set[str]) -> set[str]:
    rules = {
        "first-talk": progress.sessions >= 1,
        "streak-3": progress.best_streak >= 3,
        "streak-7": progress.best_streak >= 7,
        "words-10": progress.words_total >= 10,
        "words-50": progress.words_total >= 50,
        "minutes-60": progress.total_minutes >= 60,
        "starter-path": {lesson.key for lesson in STARTER_PATH} <= finished_lessons,
        "monthly-review": bool(progress.monthly_reviews),
    }
    return {key for key, done in rules.items() if done}


@dataclass(frozen=True)
class Notice:
    id: str
    type: str
    title: str
    text: str
    date: str


# Uygulama içi bildirimler: yalnızca o an gerçekten geçerli olan durumlar; baskıcı dil kullanılmaz.
def notices(
    progress: Progress,
    badges: list[dict],
    due_words: int,
    review_due: bool,
    prefs: dict[str, bool],
    now: datetime,
) -> list[Notice]:
    today = now.astimezone(LOCAL_TIME).date()
    items = []
    if prefs.get("daily", True) and progress.sessions and not progress.goal_met:
        left = progress.daily_goal - progress.today_minutes
        items.append(
            Notice(
                f"daily-{today}",
                "daily",
                "Bugünkü hedefin",
                f"Hedefine {left} dakika kaldı. Kısa bir konuşma yeter.",
                today.isoformat(),
            )
        )
    if prefs.get("review", True) and due_words:
        items.append(
            Notice(
                f"review-{today}",
                "review",
                "Tekrar zamanı",
                f"{due_words} kelimenin tekrar zamanı geldi. Partnerin onları konuşmada kullanır.",
                today.isoformat(),
            )
        )
    week_minutes = sum(day["minutes"] for day in progress.week)
    if prefs.get("weekly", True) and week_minutes:
        monday = today - timedelta(days=today.weekday())
        items.append(
            Notice(
                f"weekly-{monday}",
                "weekly",
                "Haftalık özet",
                f"Son 7 günde {week_minutes} dakika konuştun.",
                monday.isoformat(),
            )
        )
    if prefs.get("monthly", True) and review_due:
        items.append(
            Notice(
                f"monthly-{today:%Y-%m}",
                "monthly",
                "Aylık konuşma değerlendirmesi",
                "İsteğe bağlı değerlendirmen hazır; ana sayfadan başlat ya da ertele.",
                today.isoformat(),
            )
        )
    if prefs.get("badge", True):
        titles = {badge.key: badge.title for badge in BADGES}
        for badge in badges:
            items.append(
                Notice(
                    f"badge-{badge['key']}",
                    "badge",
                    "Yeni rozet",
                    f"{titles.get(badge['key'], badge['key'])} rozetini kazandın.",
                    local_day(badge["earned_at"]).isoformat(),
                )
            )
    return sorted(items, key=lambda item: item.date, reverse=True)
