# Oturum sonu raporu: sayılar veritabanındaki kayıtlardan hesaplanır, tahmin edilmez.
from collections import Counter
from datetime import datetime
from math import ceil

from pydantic import BaseModel

from app.db import Database


class Correction(BaseModel):
    error: str
    correction: str
    focus_area: str | None = None


class ReportWord(BaseModel):
    expression: str
    turkish_meaning: str | None = None
    cefr_level: str | None = None


class SessionReport(BaseModel):
    minutes: int
    turns: int
    start_level: str | None
    end_level: str | None
    new_words: list[ReportWord]
    corrections: list[Correction]
    focus_areas: list[str]
    summary: str
    next_focus: str | None


def build_report(db: Database, session_id: str) -> SessionReport:
    session = db.get_session(session_id)
    learner = db.get_learner(session["learner_id"])
    errors = db.session_errors(session_id)

    # Köşeli parantezle başlayan mesajlar uygulamanın iç komutlarıdır, öğrencinin turu sayılmaz.
    turns = sum(
        1
        for message in db.get_messages(session_id)
        if message["role"] == "user" and not message["content"].startswith("[")
    )
    started = datetime.fromisoformat(session["started_at"])
    ended = datetime.fromisoformat(session["ended_at"])
    areas = Counter(row["focus_area"] for row in errors if row["focus_area"])

    return SessionReport(
        minutes=max(1, ceil((ended - started).total_seconds() / 60)),
        turns=turns,
        start_level=session["start_level"],
        end_level=session["end_level"],
        new_words=[
            ReportWord(
                expression=row["expression"],
                turkish_meaning=row["turkish_meaning"],
                cefr_level=row["cefr_level"],
            )
            for row in db.session_words(session_id)
        ],
        corrections=[
            Correction(
                error=row["error"], correction=row["correction"], focus_area=row["focus_area"]
            )
            for row in errors
        ],
        focus_areas=[area for area, _ in areas.most_common()],
        summary=session["summary"],
        next_focus=learner["next_focus"],
    )
