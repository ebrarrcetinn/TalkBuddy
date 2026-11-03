# Seri, günlük hedef, haftalık dakikalar, rozetler ve bildirimlerin hesaplanmasını test eder.
from datetime import UTC, date, datetime, timedelta

from app.progress import best_streak, build, current_streak, notices

NOW = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def session(day_offset: int, minutes: int, **extra) -> dict:
    ended = NOW - timedelta(days=day_offset)
    started = ended - timedelta(minutes=minutes)
    row = {"started_at": started.isoformat(), "ended_at": ended.isoformat()}
    return row | {"lesson": None, "topic": None, "mode": "practice", "summary": None} | extra


def test_streak_counts_consecutive_days_up_to_today_or_yesterday():
    today = date(2026, 11, 2)
    days = {today - timedelta(days=n) for n in (1, 2, 3, 6)}

    assert current_streak(days, today) == 3
    assert current_streak(days | {today}, today) == 4
    assert current_streak({today - timedelta(days=2)}, today) == 0
    assert best_streak(days) == 3


def test_progress_is_built_from_real_sessions_and_words():
    sessions = [
        session(0, 4, lesson="starter-1"),
        session(0, 3, topic="Spor"),
        session(1, 10, mode="monthly", summary="Good effort."),
    ]
    words = [
        {"status": "MASTERED", "review_count": 4, "next_review": "2026-01-01"},
        {"status": "NEW", "review_count": 0, "next_review": "2026-01-01"},
    ]
    weaknesses = [{"name": "past simple", "count": 3}]

    report = build(sessions, words, weaknesses, 10, NOW)

    assert report.today_minutes == 7
    assert not report.goal_met
    assert report.streak == 2
    assert report.total_minutes == 17
    assert [day["minutes"] for day in report.week][-2:] == [10, 7]
    assert (report.words_mastered, report.words_learning, report.reviews_done) == (1, 1, 4)
    assert report.topics == ["Tanışalım", "Spor"]
    assert report.mistakes == [{"name": "past simple", "count": 3}]
    assert report.earned_badges == {"first-talk", "monthly-review"}
    assert report.words_due == 1
    assert report.advice[0].startswith("En sık düzeltilen yapın: past simple.")
    assert len(report.advice) == 3


def test_notifications_follow_preferences_and_real_state():
    report = build([session(0, 3)], [], [], 10, NOW)
    badges = [{"key": "first-talk", "earned_at": NOW.isoformat()}]

    everything = notices(report, badges, 2, True, {}, NOW)
    assert {item.type for item in everything} == {"daily", "review", "weekly", "monthly", "badge"}

    quiet = {"daily": False, "review": False, "weekly": False, "monthly": False, "badge": False}
    assert notices(report, badges, 2, True, quiet, NOW) == []


def test_new_learner_gets_no_pressure_notifications():
    report = build([], [], [], 10, NOW)

    assert notices(report, [], 0, False, {}, NOW) == []


def test_new_learner_gets_no_advice():
    assert build([], [], [], 10, NOW).advice == []
