# Öğrenme akışı: koçu çalıştırır, cevabı hafızaya işler ve bir sonraki turun bağlamını hazırlar.
import json
import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, time

from app import path, progress, vocab
from app.coach import Coach, CoachOutputError, Session, WordExplanation, parse_response
from app.db import Database
from app.level import LevelState, LexicalProfile, update
from app.plan import LearningPlan, PlanProgress
from app.report import SessionReport, build_report
from app.schemas import CoachResponse, Persona

# Klavyeyle yazılan mesajlara eklenen işaret; partner bunu ses dökümünden ayırır.
TYPED_MARK = "(Typed)"


# Kayıtlı bir mesajın ekranda görünen hali. Uygulamanın iç komutları ("[Session started…]")
# gösterilmez; partnerin JSON cevabından yalnızca söylediği metin alınır.
def shown_text(message: dict[str, str]) -> str | None:
    content = message["content"]
    if message["role"] == "user":
        if content.startswith("["):
            return None
        return content.split("\n(")[0]
    try:
        return parse_response(content).spoken_text
    except CoachOutputError:
        return None


class SessionNotFound(Exception):
    pass


# Yaş yalnızca konuyu etkiler; kelime ve cümle zorluğunu her zaman İngilizce seviyesi belirler.
AGE_GUIDANCE = {
    "0-6": "A young child, usually with a parent. Prefer topics like colours, animals, toys, "
    "family and food. Do not assume reading or writing.",
    "7-14": "A child or teenager. Prefer topics such as school, friends, science, nature and "
    "hobbies.",
    "15-20": "Any topic is fine.",
    "21-24": "Any topic is fine.",
    "25-30": "Any topic is fine.",
    "31-35": "Any topic is fine.",
    "36+": "Any topic is fine.",
}


# Partnerin bir cevabı seviyeye göre en fazla bu kadar olabilir; cevaplar okunmaz, dinlenir.
REPLY_LIMITS = {
    "A1": "2 very short sentences, about 12 words, one question",
    "A2": "2 short sentences, about 20 words, one question",
    "B1": "3 sentences, about 35 words",
    "B2": "3 sentences, about 45 words",
    "C1": "4 sentences, about 60 words",
    "C2": "4 sentences, about 60 words",
}


# Bir turun sonucu: koçun cevabı, güncel seviye, bu turda eklenen kelimeler ve (bitişte) rapor.
# Bugünün sohbeti: ekranda gösterilecek mesajlar ve varsa devam edilecek açık konuşma.
@dataclass
class TodayChat:
    open_session: dict | None = None
    messages: list[dict[str, str]] = field(default_factory=list)


@dataclass
class TurnResult:
    session_id: str
    response: CoachResponse
    level: str | None
    new_words: list[str] = field(default_factory=list)
    report: SessionReport | None = None


class Tutor:
    def __init__(
        self,
        coach: Coach,
        db: Database,
        lexicon: LexicalProfile | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        plan: LearningPlan | None = None,
        rng: random.Random | None = None,
    ):
        self._coach = coach
        self._db = db
        self._lexicon = lexicon or LexicalProfile({})
        self._clock = clock
        self._plan = plan or LearningPlan([])
        self._rng = rng or random.Random()
        self._explanations: dict[str, WordExplanation] = {}

    # Partner verilmezse öğrencinin profilde seçtiği partner kullanılır.
    def start(
        self,
        learner_id: str,
        persona: Persona | None = None,
        topic: str | None = None,
        minutes: int | None = None,
        mode: str = "practice",
        lesson: str | None = None,
    ) -> TurnResult:
        now = self._clock().isoformat()
        learner = self._db.get_learner(learner_id)
        if persona is None and learner is not None:
            persona = Persona(learner["persona"])
        self._db.save_learner(learner_id, persona or Persona.FEMALE, now)
        persona = Persona(self._db.get_learner(learner_id)["persona"])
        start_level = self._db.get_learner(learner_id)["level"]

        if mode == "monthly":
            minutes = minutes or 15
        context = self._context(learner_id, topic=topic, minutes=minutes, mode=mode, lesson=lesson)
        session = Session(persona=persona, learner_context=context)
        response = self._coach.start(session)

        # Oturum yalnızca koç başarıyla cevap verirse kaydedilir.
        session_id = uuid.uuid4().hex
        self._db.create_session(
            session_id, learner_id, persona, start_level, now, topic, minutes, mode, lesson
        )
        self._db.add_messages(session_id, session.history)
        return self._record(session_id, learner_id, response, user_text=None)

    # Yazılan mesaj "(Typed)" işaretiyle gider; partner ses tanıma kurallarını ona uygulamaz.
    def reply(
        self,
        session_id: str,
        text: str,
        alternatives: list[str] | None = None,
        typed: bool = False,
    ) -> TurnResult:
        row, session = self._load(session_id)
        others = [item.strip() for item in alternatives or [] if item.strip() and item != text]
        message = text
        if typed:
            message += f"\n{TYPED_MARK}"
        elif others:
            message += f"\n(Other possible transcriptions: {' | '.join(others)})"
        response = self._coach.reply(session, message)
        self._db.add_messages(session_id, session.history[-2:])
        return self._record(session_id, row["learner_id"], response, user_text=text)

    def end(self, session_id: str) -> TurnResult:
        row, session = self._load(session_id)
        response = self._coach.end(session)
        self._db.add_messages(session_id, session.history[-2:])
        result = self._record(session_id, row["learner_id"], response, user_text=None)

        summary = response.memory_update.session_summary or response.spoken_text
        self._db.end_session(session_id, result.level, summary, self._clock().isoformat())
        self._db.save_notes(row["learner_id"], last_summary=summary)
        result.report = build_report(self._db, session_id)
        return result

    def today(self, learner_id: str) -> TodayChat:
        now = self._clock()
        local = progress.LOCAL_TIME
        midnight = datetime.combine(now.astimezone(local).date(), time(), local)
        chat = TodayChat()
        for row in self._db.sessions_since(learner_id, midnight.astimezone(UTC).isoformat()):
            for message in self._db.get_messages(row["id"]):
                text = shown_text(message)
                if text:
                    chat.messages.append({"role": message["role"], "text": text})
            if row["ended_at"] is None:
                chat.open_session = {
                    key: row[key] for key in ("id", "topic", "lesson", "mode", "planned_minutes")
                }
        return chat

    # Açık bir oturumu veritabanından geri kurar; sunucu yeniden başlasa da sohbet devam eder.
    def _load(self, session_id: str) -> tuple:
        row = self._db.get_session(session_id)
        if row is None or row["ended_at"] is not None:
            raise SessionNotFound(session_id)
        session = Session(
            persona=Persona(row["persona"]),
            history=self._db.get_messages(session_id),
            learner_context=self._context(row["learner_id"], session=row),
        )
        return row, session

    # Koçun cevabındaki öğrenme bilgilerini kaydeder: kelimeler, hatalar, zayıf konular, seviye.
    def _record(
        self, session_id: str, learner_id: str, response: CoachResponse, user_text: str | None
    ) -> TurnResult:
        now = self._clock()
        new_words = self._save_words(learner_id, session_id, response, now)
        self._save_errors(learner_id, session_id, response, now)

        memory = response.memory_update
        self._db.save_notes(learner_id, last_topic=memory.last_topic, next_focus=memory.next_focus)
        level = self._save_level(learner_id, response.current_level, user_text)
        return TurnResult(session_id, response, level, new_words)

    def _save_words(
        self, learner_id: str, session_id: str, response: CoachResponse, now: datetime
    ) -> list[str]:
        today = now.date()
        added = []
        for entry in response.vocab_box_update:
            expression = entry.expression.strip()
            if not expression or vocab.is_sentence(expression):
                continue
            existing = self._db.get_word(learner_id, expression)
            if existing:
                self._db.fill_word(
                    existing["id"], entry.turkish_meaning, entry.cefr_level, entry.example
                )
                continue
            self._db.add_word(
                learner_id,
                session_id,
                expression,
                entry.turkish_meaning,
                entry.cefr_level,
                entry.example,
                status=vocab.status_for(0),
                next_review=vocab.next_review(0, today).isoformat(),
                now=now.isoformat(),
            )
            added.append(expression)

        # Tekrar sayısı yalnızca tekrar günü gelmiş kelimelerde artar; aynı gün ilerletilemez.
        for expression in response.memory_update.reviewed_vocabulary:
            word = self._db.get_word(learner_id, expression.strip())
            if word is None or word["next_review"] > today.isoformat():
                continue
            count = word["review_count"] + 1
            self._db.save_review(
                word["id"],
                count,
                vocab.status_for(count),
                vocab.next_review(count, today).isoformat(),
            )
        return added

    def _save_errors(
        self, learner_id: str, session_id: str, response: CoachResponse, now: datetime
    ) -> None:
        tracking = response.error_tracking
        weaknesses = {name.strip().lower() for name in response.memory_update.grammar_weaknesses}

        if tracking.latest_error and tracking.corrected_version:
            previous = self._db.session_errors(session_id)[-1:]
            pair = (tracking.latest_error, tracking.corrected_version)
            # Koç tekrar beklerken aynı hatayı yeniden bildirirse ikinci kez kaydedilmez.
            if not previous or (previous[0]["error"], previous[0]["correction"]) != pair:
                self._db.add_error(
                    learner_id, session_id, *pair, tracking.focus_area, now.isoformat()
                )
                if tracking.focus_area:
                    weaknesses.add(tracking.focus_area.strip().lower())

        for name in weaknesses - {""}:
            self._db.bump_weakness(learner_id, name)
        for name in response.memory_update.mastered_structures:
            self._db.master_weakness(learner_id, name.strip().lower())

    def _save_level(self, learner_id: str, claude_level: str, user_text: str | None) -> str | None:
        learner = self._db.get_learner(learner_id)
        state = LevelState(
            learner["level_score"],
            learner["level"],
            learner["pending_level"],
            learner["pending_turns"],
        )
        lexical = self._lexicon.score(user_text) if user_text else None
        new_state = update(state, claude_level, lexical)
        if new_state != state:
            self._db.save_level(
                learner_id,
                new_state.level,
                new_state.score,
                new_state.pending,
                new_state.pending_turns,
            )
        return new_state.level

    # Koça verilecek öğrenci profili: dokümandaki "kayıtlı profili koça ilet" kuralı.
    # session verilirse konuşma sürüyordur; konu ve süre o oturumun kaydından okunur.
    def _context(
        self,
        learner_id: str,
        session=None,
        topic: str | None = None,
        minutes: int | None = None,
        mode: str = "practice",
        lesson: str | None = None,
    ) -> str:
        learner = self._db.get_learner(learner_id)
        user = self._db.get_user(learner_id)
        in_progress = session is not None
        if in_progress:
            topic, minutes, mode = session["topic"], session["planned_minutes"], session["mode"]
            lesson = session["lesson"]
        earlier_sessions = self._db.count_sessions(learner_id) - (1 if in_progress else 0)
        first_conversation = earlier_sessions == 0
        lines = []

        if user is not None:
            lines.append(f"Learner first name: {user['first_name']}")
            if user["age_group"]:
                lines.append(
                    f"Learner age group: {user['age_group']}. {AGE_GUIDANCE[user['age_group']]} "
                    "Age never changes difficulty; the English level does."
                )
            if user["interests"]:
                lines.append(f"Learner interests: {user['interests']}")
            if user["goal"]:
                lines.append(f"Learner's goal for learning English (in Turkish): {user['goal']}")

        if learner["level"] is None:
            lines.append(
                "Learner profile: new learner, no saved level. Estimate the level gently through "
                "natural conversation; do not run a test."
            )
        elif first_conversation:
            start = user["start_level"] if user is not None else learner["level"]
            lines.append(
                f"Learner profile: first conversation. Level chosen during onboarding: {start}. "
                "Do not run a placement test."
            )
        else:
            lines.append("Learner profile: returning learner. Do not run a placement test.")
        if learner["level"]:
            lines.append(f"Current working level: {learner['level']}. Adapt your language to it.")
            lines.append(f"Reply length limit: {REPLY_LIMITS[learner['level']]}.")

        if learner["last_summary"]:
            lines.append(f"Previous session summary: {learner['last_summary']}")
        if learner["last_topic"]:
            lines.append(f"Last topic: {learner['last_topic']}")
        if learner["next_focus"]:
            lines.append(f"Planned focus: {learner['next_focus']}")

        weaknesses = self._db.top_weaknesses(learner_id)
        if weaknesses:
            items = ", ".join(f"{row['name']} ({row['count']})" for row in weaknesses)
            lines.append(f"Recurring weaknesses: {items}")
        errors = self._db.recent_errors(learner_id)
        if errors:
            items = "; ".join(f'"{row["error"]}" -> "{row["correction"]}"' for row in errors)
            lines.append(f"Recently corrected: {items}")
        due = self._db.due_words(learner_id, self._clock().date().isoformat())
        if due:
            lines.append(f"Vocabulary due for review: {', '.join(due)}")

        if mode == "monthly":
            lines.append(
                "This is the optional MONTHLY SPEAKING REVIEW, not a normal practice session. "
                "Follow the MONTHLY SPEAKING REVIEW rules."
            )
        elif not in_progress:
            suggested = self._suggest_words(learner_id, learner["level"])
            if suggested:
                lines.append(
                    "New words from the learner's level plan (Oxford list, not yet known): "
                    f"{', '.join(suggested)}. Bring in three to five of them naturally."
                )
        if lesson in path.LESSONS:
            step = path.LESSONS[lesson]
            lines.append(
                f"Guided beginner conversation: {step.focus} Keep it very easy and short. If the "
                "learner is stuck, offer two or three ready phrases they can use in their answer."
            )
        if topic:
            lines.append(f"Topic the learner chose for this conversation: {topic}.")
        if minutes:
            lines.append(f"Planned length of this conversation: {minutes} minutes.")
            if in_progress:
                started = datetime.fromisoformat(session["started_at"])
                used = int((self._clock() - started).total_seconds() // 60)
                lines.append(f"Time used so far: {used} of {minutes} minutes.")
                if used >= minutes - 1:
                    lines.append(
                        "Time is nearly up. Wrap up now: briefly recap the new words and "
                        "suggest ending the conversation."
                    )
        if in_progress:
            lines.append(
                "This conversation is already in progress. You have already greeted the learner. "
                "Do not greet them, introduce yourself or ask their name again; continue from "
                "their last message."
            )
        return "\n".join(lines)

    # Değerlendirmede gösterilen kelimeler: işaretlenenler (bilinen) ve işaretlenmeyenler.
    def _assessment_words(self, learner_id: str) -> tuple[set[str], set[str]]:
        state = self._db.get_assessment(learner_id)
        if state is None:
            return set(), set()
        shown = {word.lower() for section in state["sections"] for word in section}
        ticked = {word.lower() for section in state["selections"] for word in section}
        return ticked, shown - ticked

    def _vocabulary_words(self, learner_id: str) -> tuple[set[str], set[str]]:
        rows = self._db.list_words(learner_id)
        mastered = {row["expression"].lower() for row in rows if row["status"] == "MASTERED"}
        return mastered, {row["expression"].lower() for row in rows} - mastered

    def _suggest_words(self, learner_id: str, level: str | None) -> list[str]:
        ticked, unticked = self._assessment_words(learner_id)
        mastered, learning = self._vocabulary_words(learner_id)
        exclude = ticked | mastered | learning
        return self._plan.suggest(level, exclude, unticked, 8, self._rng)

    # Günün önerilen konuşması: başlangıç rotasının sıradaki adımı ya da bir ilgi alanı.
    def suggestion(self, learner_id: str) -> path.Suggestion:
        learner = self._db.get_learner(learner_id)
        user = self._db.get_user(learner_id)
        sessions = self._db.finished_sessions(learner_id)
        finished = {row["lesson"] for row in sessions}
        interests = [i for i in (user["interests"] or "").split(", ") if i] if user else []
        # Rotasyon için son konuşmanın seçilen konusu kullanılır (partnerin notu değil).
        last_topic = sessions[-1]["topic"] if sessions else None
        return path.suggest(learner["level"], finished, interests, last_topic)

    # Gelişim özeti; yeni kazanılan rozetler bu sırada kaydedilir.
    def progress_report(self, learner_id: str) -> progress.Progress:
        user = self._db.get_user(learner_id)
        daily_goal = (user["daily_goal"] if user else None) or progress.DEFAULT_DAILY_GOAL
        now = self._clock()
        report = progress.build(
            self._db.finished_sessions(learner_id),
            self._db.list_words(learner_id),
            self._db.top_weaknesses(learner_id, limit=5),
            daily_goal,
            now,
        )
        if report.earned_badges:
            self._db.add_badges(learner_id, report.earned_badges, now.isoformat())
        return report

    def notification_prefs(self, learner_id: str) -> dict[str, bool]:
        user = self._db.get_user(learner_id)
        saved = (
            json.loads(user["notification_prefs"]) if user and user["notification_prefs"] else {}
        )
        return {kind: saved.get(kind, True) for kind in progress.NOTIFICATION_TYPES}

    # Bildirimler ve okunmamış sayısı: son açılıştan sonraki tarihli bildirimler okunmamıştır.
    def notifications(self, learner_id: str, review_due: bool) -> tuple[list, int]:
        report = self.progress_report(learner_id)
        now = self._clock()
        badges = [dict(row) for row in self._db.badges(learner_id)]
        items = progress.notices(
            report,
            badges,
            self.due_count(learner_id),
            review_due,
            self.notification_prefs(learner_id),
            now,
        )
        seen = self._db.get_user(learner_id)["notifications_seen_at"]
        seen_day = progress.local_day(seen).isoformat() if seen else None
        unread = sum(1 for item in items if seen_day is None or item.date > seen_day)
        return items, unread

    def badges(self, learner_id: str):
        return self._db.badges(learner_id)

    def mark_notifications_seen(self, learner_id: str) -> None:
        self._db.update_user(learner_id, notifications_seen_at=self._clock().isoformat())

    def save_settings(
        self, learner_id: str, daily_goal: int | None, prefs: dict[str, bool] | None
    ) -> None:
        fields = {}
        if daily_goal is not None:
            fields["daily_goal"] = daily_goal
        if prefs is not None:
            merged = self.notification_prefs(learner_id) | {
                kind: bool(value)
                for kind, value in prefs.items()
                if kind in progress.NOTIFICATION_TYPES
            }
            fields["notification_prefs"] = json.dumps(merged)
        if fields:
            self._db.update_user(learner_id, **fields)

    def finished_count(self, learner_id: str) -> int:
        return len(self._db.finished_sessions(learner_id))

    def plan_progress(self, learner_id: str) -> PlanProgress | None:
        learner = self._db.get_learner(learner_id)
        ticked, _ = self._assessment_words(learner_id)
        mastered, learning = self._vocabulary_words(learner_id)
        return self._plan.progress(learner["level"], ticked | mastered, learning)

    # Dökümdeki kelimenin anlamı: önce kelime listesine, sonra önbelleğe, en son partnere bakılır.
    def explain_word(self, learner_id: str, word: str, sentence: str) -> WordExplanation:
        saved = self._db.get_word(learner_id, word)
        if saved is not None and saved["turkish_meaning"]:
            return WordExplanation(
                turkish_meaning=saved["turkish_meaning"], example=saved["example"] or ""
            )
        key = word.lower()
        if key not in self._explanations:
            self._explanations[key] = self._coach.explain(word, sentence)
        return self._explanations[key]

    def word_level(self, word: str) -> str | None:
        return self._lexicon.level_of(word.lower())

    def learner(self, learner_id: str):
        return self._db.get_learner(learner_id)

    def session_owner(self, session_id: str) -> str | None:
        row = self._db.get_session(session_id)
        return row["learner_id"] if row else None

    # Öğrencinin konuşma dökümünden dokunarak kaydettiği kelime. Yeni eklendiyse True döner.
    def save_word(self, learner_id: str, expression: str) -> bool:
        expression = expression.strip()
        if not expression or self._db.get_word(learner_id, expression):
            return False
        now = self._clock()
        # Kelimeye dokunulduğunda gösterilen açıklama kayda da yazılır.
        explanation = self._explanations.get(expression.lower())
        self._db.add_word(
            learner_id,
            None,
            expression,
            explanation.turkish_meaning if explanation else None,
            self.word_level(expression),
            explanation.example if explanation else None,
            status=vocab.status_for(0),
            next_review=vocab.next_review(0, now.date()).isoformat(),
            now=now.isoformat(),
        )
        return True

    def delete_word(self, learner_id: str, word_id: int) -> bool:
        return self._db.delete_word(learner_id, word_id)

    def due_count(self, learner_id: str) -> int:
        return len(self._db.due_words(learner_id, self._clock().date().isoformat(), limit=1000))

    def vocabulary(self, learner_id: str):
        return self._db.list_words(learner_id)

    # Türkçe anlamı eksik kayıtları (partnerin boş bıraktığı ya da eski kayıtlar) tamamlar.
    # Bir kaydın açıklaması alınamazsa o kayıt atlanır, diğerlerine devam edilir.
    def fill_meanings(self, learner_id: str, limit: int = 10) -> None:
        missing = [w for w in self._db.list_words(learner_id) if not w["turkish_meaning"]]
        for word in missing[:limit]:
            sentence = word["example"] or ""
            try:
                explanation = self.explain_word(learner_id, word["expression"], sentence)
            except CoachOutputError:
                continue
            self._db.fill_word(word["id"], explanation.turkish_meaning, None, explanation.example)
