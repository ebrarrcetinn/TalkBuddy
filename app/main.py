# Web uygulaması: tarayıcıdan gelen istekleri karşılar, hesap ve öğrenme akışlarına iletir.
import logging
import sqlite3
import time
from pathlib import Path
from typing import Annotated, Literal

from anthropic import APIError
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import assessment, vocab, wordlist
from app.accounts import (
    AGE_GROUPS,
    GOALS,
    INTERESTS,
    PHOTO_MAX_BYTES,
    AccountError,
    Accounts,
)
from app.auth import ConsoleMailer, SmtpMailer
from app.coach import Coach, CoachOutputError
from app.config import load_settings
from app.db import Database
from app.level import LexicalProfile
from app.llm import AnthropicClient
from app.path import LESSONS
from app.plan import LearningPlan
from app.progress import BADGES
from app.report import Correction, SessionReport
from app.schemas import Persona
from app.speech import Transcriber, WhisperTranscriber, whisper_installed
from app.tutor import SessionNotFound, TurnResult, Tutor

WEB_DIR = Path(__file__).parent.parent / "web"
SESSION_COOKIE = "talkbuddy_session"


# İstek gövdeleri. Form alanları boş gelebilir; kontroller Türkçe hata mesajlarıyla yapılır.
class RegisterRequest(BaseModel):
    first_name: str = ""
    last_name: str = ""
    phone: str = ""
    email: str = ""
    password: str = ""
    password_confirm: str = ""


class LoginRequest(BaseModel):
    email: str = ""
    password: str = ""
    # "Beni hatırla" seçili değilse oturum tarayıcı kapanınca biter.
    remember: bool = True


class ForgotRequest(BaseModel):
    email: str = ""


class ResetRequest(BaseModel):
    token: str
    password: str = ""
    password_confirm: str = ""


class PasswordChangeRequest(BaseModel):
    current_password: str = ""
    password: str = ""
    password_confirm: str = ""


class NameRequest(BaseModel):
    first_name: str = Field(max_length=200)
    last_name: str = Field(max_length=200)


class AgeRequest(BaseModel):
    age_group: str


class GoalRequest(BaseModel):
    goal: str


class SettingsRequest(BaseModel):
    daily_goal: Literal[5, 10, 15, 20] | None = None
    notifications: dict[str, bool] | None = None


class BadgeOut(BaseModel):
    key: str
    title: str
    description: str
    earned: bool
    earned_at: str | None


class NoticeOut(BaseModel):
    id: str
    type: str
    title: str
    text: str
    date: str


class NotificationsOut(BaseModel):
    items: list[NoticeOut]
    unread: int


class SuggestionOut(BaseModel):
    kind: str
    title: str
    description: str
    minutes: int
    lesson: str | None
    topic: str | None
    step: int | None
    total_steps: int | None


class LevelRequest(BaseModel):
    level: str


class PartnerRequest(BaseModel):
    partner: Persona


class InterestsRequest(BaseModel):
    interests: list[str]


class WordRequest(BaseModel):
    expression: str = Field(min_length=1, max_length=80)


class SectionRequest(BaseModel):
    selected: list[str]


# Konu ve süre isteğe bağlıdır; konu seçilmezse partner ilgi alanlarından birini seçer.
class StartRequest(BaseModel):
    topic: str | None = None
    minutes: Literal[3, 5, 10, 15, 20] | None = None
    mode: Literal["practice", "monthly"] = "practice"
    lesson: str | None = None


class EmailChangeRequest(BaseModel):
    new_email: str = ""
    password: str = ""


class TokenRequest(BaseModel):
    token: str


class ExplainRequest(BaseModel):
    word: str = Field(min_length=1, max_length=40)
    sentence: str = Field(default="", max_length=400)


class ExplainReply(BaseModel):
    word: str
    turkish_meaning: str
    example: str
    level: str | None


class TranscriptOut(BaseModel):
    text: str
    language: str


class PlanOut(BaseModel):
    level: str
    total: int
    known: int
    learning: int
    percent: int


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    # Ses tanımanın aynı söz için önerdiği diğer yazımlar; partner anlamı çıkarırken kullanır.
    alternatives: list[Annotated[str, Field(max_length=2000)]] = Field(default=[], max_length=3)
    # Mesaj klavyeyle yazıldıysa true; konuşmadan gelen dökümden ayrılır.
    typed: bool = False


# Cevaplar


class ProgressOut(BaseModel):
    today_minutes: int
    daily_goal: int
    goal_met: bool
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
    advice: list[str]
    plan: PlanOut | None
    badges: list[BadgeOut]


class Profile(BaseModel):
    first_name: str
    last_name: str
    email: str
    age_group: str | None
    goal: str | None
    interests: list[str]
    partner: Persona
    start_level: str | None
    level: str | None
    onboarding_step: str
    assessment_available: bool
    plan: PlanOut | None
    level_pending: str | None
    level_pending_turns: int
    review_due: bool
    speech_engine: Literal["whisper", "browser"]
    finished_sessions: int
    suggestion: SuggestionOut
    daily_goal: int
    today_minutes: int
    streak: int
    unread_notifications: int
    notification_prefs: dict[str, bool]
    due_words: int
    last_topic: str | None
    last_summary: str | None
    photo_version: str | None


class AssessmentState(BaseModel):
    section: int
    total_sections: int
    level: str | None
    words: list[str]
    completed: bool


class LevelScoreOut(BaseModel):
    level: str
    selected: int
    total: int
    passed: bool


class AssessmentResultOut(BaseModel):
    scores: list[LevelScoreOut]
    recommended_level: str
    inconsistent: bool


# Tarayıcıya giden konuşma cevabı: koçun JSON'undan sadece ekranın ihtiyaç duyduğu alanlar.
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class OpenSession(BaseModel):
    id: str
    topic: str | None
    lesson: str | None
    mode: str
    planned_minutes: int | None


# Bugünün sohbeti: ekrandan çıkıp dönen öğrenci mesajlarını görür, açık konuşmaya devam eder.
class TodayOut(BaseModel):
    open_session: OpenSession | None
    messages: list[ChatMessage]


class TurnReply(BaseModel):
    session_id: str
    spoken_text: str
    level: str
    phase: str
    awaiting_repetition: bool
    expression: str
    speech_rate: str | None
    correction: Correction | None
    new_words: list[str]

    @classmethod
    def from_result(cls, result: TurnResult) -> "TurnReply":
        response = result.response
        tracking = response.error_tracking
        correction = None
        if tracking.latest_error and tracking.corrected_version:
            correction = Correction(
                error=tracking.latest_error,
                correction=tracking.corrected_version,
                focus_area=tracking.focus_area,
            )
        return cls(
            session_id=result.session_id,
            spoken_text=response.spoken_text,
            level=result.level or "Undetermined",
            phase=response.session_state.phase,
            awaiting_repetition=response.session_state.awaiting_repetition,
            expression=response.expression,
            speech_rate=response.speech_rate,
            correction=correction,
            new_words=result.new_words,
        )


class EndReply(TurnReply):
    report: SessionReport


class WordItem(BaseModel):
    id: int
    expression: str
    turkish_meaning: str | None
    cefr_level: str | None
    example: str | None
    status: str
    review_count: int
    next_review: str
    kind: str


# Tarayıcı stil ve kod dosyalarını her açılışta sunucuya sorar; dosya değişmediyse yeniden
# indirmez (304). Böylece güncellemeden sonra yeni sayfa eski kodla açılmaz.
class FreshStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Konuşmanın hangi aşamasının ne kadar sürdüğü sunucu terminaline yazılır (içerik yazılmaz).
logger = logging.getLogger("talkbuddy")

# Bir konuşma kaydı en fazla bu kadar olabilir (yaklaşık bir dakikalık sıkıştırılmış ses).
MAX_AUDIO_BYTES = 2_000_000


# Giriş yapmış kullanıcıyı çerezdeki oturum anahtarından bulur.
def current_user(request: Request) -> sqlite3.Row:
    token = request.cookies.get(SESSION_COOKIE)
    user = request.app.state.accounts.user_for_token(token) if token else None
    if user is None:
        raise HTTPException(401, "Devam etmek için giriş yapmalısın.")
    return user


User = Annotated[sqlite3.Row, Depends(current_user)]


# Kurulumu bitirmemiş kullanıcı konuşmaya başlayamaz.
def ready_user(user: User) -> sqlite3.Row:
    if user["onboarding_step"] != "done":
        raise HTTPException(409, "Önce ilk kurulumu tamamla.")
    return user


ReadyUser = Annotated[sqlite3.Row, Depends(ready_user)]


def create_app(
    tutor: Tutor,
    accounts: Accounts,
    cookie_secure: bool = False,
    transcriber: Transcriber | None = None,
) -> FastAPI:
    app = FastAPI(title="TalkBuddy")
    app.state.accounts = accounts

    # Hesap hataları Türkçe mesaj ve alan bazlı hatalarla döner.
    @app.exception_handler(AccountError)
    def account_error(_: Request, exc: AccountError) -> JSONResponse:
        return JSONResponse({"detail": exc.message, "fields": exc.fields}, status_code=exc.status)

    def set_session(response: Response, token: str, remember: bool = True) -> None:
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=60 * 60 * 24 * 30 if remember else None,
            httponly=True,
            samesite="lax",
            secure=cookie_secure,
        )

    def plan_out(progress) -> PlanOut | None:
        if progress is None:
            return None
        return PlanOut(**vars(progress), percent=progress.percent)

    def profile(user) -> Profile:
        learner = tutor.learner(user["id"])
        if learner is None:
            raise HTTPException(404, "Öğrenci kaydı bulunamadı.")
        review_due = accounts.review_due(user["id"])
        report = tutor.progress_report(user["id"])
        photo = accounts.photo(user["id"])
        return Profile(
            first_name=user["first_name"],
            last_name=user["last_name"],
            email=user["email"],
            age_group=user["age_group"],
            goal=user["goal"],
            interests=[i for i in (user["interests"] or "").split(", ") if i],
            partner=learner["persona"],
            start_level=user["start_level"],
            level=learner["level"],
            onboarding_step=user["onboarding_step"],
            assessment_available=accounts.assessment_available(),
            plan=plan_out(tutor.plan_progress(user["id"])),
            level_pending=learner["pending_level"],
            level_pending_turns=learner["pending_turns"],
            review_due=review_due,
            speech_engine="whisper" if transcriber else "browser",
            finished_sessions=tutor.finished_count(user["id"]),
            suggestion=SuggestionOut(**vars(tutor.suggestion(user["id"]))),
            daily_goal=report.daily_goal,
            today_minutes=report.today_minutes,
            streak=report.streak,
            unread_notifications=tutor.notifications(user["id"], review_due)[1],
            notification_prefs=tutor.notification_prefs(user["id"]),
            due_words=tutor.due_count(user["id"]),
            last_topic=learner["last_topic"],
            last_summary=learner["last_summary"],
            photo_version=photo["updated_at"] if photo else None,
        )

    # Hesap

    @app.post("/api/auth/register", status_code=201)
    def register(body: RegisterRequest, response: Response) -> dict[str, str]:
        token = accounts.register(
            body.first_name,
            body.last_name,
            body.phone,
            body.email,
            body.password,
            body.password_confirm,
        )
        set_session(response, token)
        return {"status": "ok"}

    @app.post("/api/auth/login")
    def login(body: LoginRequest, response: Response) -> dict[str, str]:
        set_session(response, accounts.login(body.email, body.password), body.remember)
        return {"status": "ok"}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response) -> dict[str, str]:
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            accounts.logout(token)
        response.delete_cookie(SESSION_COOKIE)
        return {"status": "ok"}

    @app.post("/api/auth/forgot")
    def forgot(body: ForgotRequest) -> dict[str, str]:
        accounts.request_password_reset(body.email)
        return {"message": "Bu e-posta adresi kayıtlıysa şifre sıfırlama bağlantısı gönderildi."}

    @app.post("/api/auth/reset")
    def reset(body: ResetRequest) -> dict[str, str]:
        accounts.reset_password(body.token, body.password, body.password_confirm)
        return {"message": "Şifren güncellendi. Yeni şifrenle giriş yapabilirsin."}

    @app.put("/api/me/password")
    def change_password(
        body: PasswordChangeRequest, user: User, response: Response
    ) -> dict[str, str]:
        token = accounts.change_password(
            user["id"], body.current_password, body.password, body.password_confirm
        )
        set_session(response, token)
        return {"message": "Şifren güncellendi."}

    @app.put("/api/me/name")
    def set_name(body: NameRequest, user: User) -> Profile:
        accounts.set_name(user["id"], body.first_name, body.last_name)
        return profile(accounts.user(user["id"]))

    # Profil fotoğrafı yalnızca sahibine gösterilir; ham resim gövdesi olarak gönderilir.
    @app.put("/api/me/photo")
    async def save_photo(request: Request, user: User) -> Profile:
        data = await request.body()
        if len(data) > PHOTO_MAX_BYTES:
            raise HTTPException(413, "Fotoğraf çok büyük. Daha küçük bir fotoğraf seç.")
        content_type = request.headers.get("content-type", "").split(";")[0].strip()
        accounts.save_photo(user["id"], content_type, data)
        return profile(accounts.user(user["id"]))

    @app.get("/api/me/photo")
    def photo(user: User) -> Response:
        saved = accounts.photo(user["id"])
        if saved is None:
            raise HTTPException(404, "Profil fotoğrafı yok.")
        return Response(
            saved["data"],
            media_type=saved["content_type"],
            headers={"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff"},
        )

    @app.delete("/api/me/photo")
    def delete_photo(user: User) -> Profile:
        accounts.delete_photo(user["id"])
        return profile(accounts.user(user["id"]))

    @app.put("/api/me/email")
    def change_email(body: EmailChangeRequest, user: User) -> dict[str, str]:
        accounts.request_email_change(user["id"], body.new_email, body.password)
        return {"message": "Onay bağlantısı yeni e-posta adresine gönderildi."}

    @app.post("/api/auth/email/confirm")
    def confirm_email(body: TokenRequest) -> dict[str, str]:
        accounts.confirm_email_change(body.token)
        return {"message": "E-posta adresin güncellendi."}

    @app.post("/api/me/review/snooze")
    def snooze_review(user: User) -> dict[str, str]:
        accounts.snooze_review(user["id"])
        return {"message": "Aylık değerlendirmeyi bir hafta sonra yeniden hatırlatacağız."}

    # Gelişim: seri, günlük hedef, haftalık dakikalar, kelimeler, sık hatalar ve rozetler.
    @app.get("/api/me/progress")
    def get_progress(user: User) -> ProgressOut:
        report = tutor.progress_report(user["id"])
        earned = {row["key"]: row["earned_at"] for row in tutor.badges(user["id"])}
        badges = [
            BadgeOut(
                key=badge.key,
                title=badge.title,
                description=badge.description,
                earned=badge.key in earned,
                earned_at=earned.get(badge.key),
            )
            for badge in BADGES
        ]
        fields = {
            name: getattr(report, name)
            for name in ProgressOut.model_fields
            if name not in {"goal_met", "badges", "plan"}
        }
        return ProgressOut(
            **fields,
            goal_met=report.goal_met,
            plan=plan_out(tutor.plan_progress(user["id"])),
            badges=badges,
        )

    @app.get("/api/me/notifications")
    def get_notifications(user: User) -> NotificationsOut:
        items, unread = tutor.notifications(user["id"], accounts.review_due(user["id"]))
        return NotificationsOut(items=[NoticeOut(**vars(item)) for item in items], unread=unread)

    @app.post("/api/me/notifications/seen")
    def notifications_seen(user: User) -> dict[str, str]:
        tutor.mark_notifications_seen(user["id"])
        return {"status": "ok"}

    @app.put("/api/me/settings")
    def save_settings(body: SettingsRequest, user: User) -> Profile:
        tutor.save_settings(user["id"], body.daily_goal, body.notifications)
        return profile(accounts.user(user["id"]))

    @app.delete("/api/me/history")
    def delete_history(user: User) -> dict[str, str]:
        accounts.delete_history(user["id"])
        return {"message": "Konuşma geçmişin silindi."}

    # Profil ve ilk kurulum

    @app.get("/api/me")
    def me(user: User) -> Profile:
        return profile(user)

    @app.get("/api/age-groups")
    def age_groups() -> list[str]:
        return AGE_GROUPS

    @app.get("/api/interests")
    def interests() -> list[str]:
        return INTERESTS

    @app.get("/api/goals")
    def goals() -> list[str]:
        return GOALS

    @app.put("/api/me/goal")
    def set_goal(body: GoalRequest, user: User) -> Profile:
        accounts.set_goal(user["id"], body.goal)
        return profile(accounts.user(user["id"]))

    @app.put("/api/me/age-group")
    def set_age_group(body: AgeRequest, user: User) -> Profile:
        accounts.set_age_group(user["id"], body.age_group)
        return profile(accounts.user(user["id"]))

    @app.put("/api/me/level")
    def set_level(body: LevelRequest, user: User) -> Profile:
        accounts.set_level(user["id"], body.level)
        return profile(accounts.user(user["id"]))

    @app.put("/api/me/partner")
    def set_partner(body: PartnerRequest, user: User) -> Profile:
        accounts.set_partner(user["id"], body.partner)
        return profile(accounts.user(user["id"]))

    @app.put("/api/me/interests")
    def set_interests(body: InterestsRequest, user: User) -> Profile:
        accounts.set_interests(user["id"], body.interests)
        return profile(accounts.user(user["id"]))

    # Başlangıç kelime değerlendirmesi

    def assessment_state(state: dict) -> AssessmentState:
        index = state["current"]
        total = len(state["sections"])
        completed = state["completed_at"] is not None
        return AssessmentState(
            section=index,
            total_sections=total,
            level=None if completed else assessment.LEVELS[index],
            words=[] if completed else state["sections"][index],
            completed=completed,
        )

    @app.get("/api/assessment")
    def get_assessment(user: User) -> AssessmentState:
        return assessment_state(accounts.assessment_state(user["id"]))

    @app.post("/api/assessment/sections/{index}")
    def submit_section(index: int, body: SectionRequest, user: User):
        return assessment_state(accounts.submit_section(user["id"], index, body.selected))

    @app.get("/api/assessment/result")
    def assessment_result(user: User) -> AssessmentResultOut:
        result = accounts.assessment_result(user["id"])
        return AssessmentResultOut(
            scores=[LevelScoreOut(**vars(score)) for score in result.scores],
            recommended_level=result.recommended_level,
            inconsistent=result.inconsistent,
        )

    # Konuşma

    # Akışı çalıştırır; koç cevap veremezse sade bir hata, oturum yoksa 404 döner.
    def run(action) -> TurnResult:
        try:
            return action()
        except SessionNotFound as exc:
            raise HTTPException(404, "Konuşma bulunamadı.") from exc
        except (CoachOutputError, APIError) as exc:
            raise HTTPException(502, "Partnerin şu an cevap veremedi. Tekrar dener misin?") from exc

    # Her kullanıcı yalnızca kendi konuşmasına erişebilir.
    def own_session(session_id: str, user) -> None:
        if tutor.session_owner(session_id) != user["id"]:
            raise HTTPException(404, "Konuşma bulunamadı.")

    @app.post("/api/sessions")
    def start_session(user: ReadyUser, body: StartRequest | None = None) -> TurnReply:
        body = body or StartRequest()
        if body.topic is not None and body.topic not in INTERESTS:
            raise HTTPException(422, "Geçerli bir konu seçin.")
        if body.lesson is not None and body.lesson not in LESSONS:
            raise HTTPException(422, "Geçerli bir ders seçin.")
        return TurnReply.from_result(
            run(
                lambda: tutor.start(
                    user["id"],
                    topic=body.topic,
                    minutes=body.minutes,
                    mode=body.mode,
                    lesson=body.lesson,
                )
            )
        )

    @app.get("/api/sessions/today")
    def today_chat(user: ReadyUser) -> TodayOut:
        chat = tutor.today(user["id"])
        return TodayOut.model_validate(
            {"open_session": chat.open_session, "messages": chat.messages}
        )

    @app.post("/api/sessions/{session_id}/messages")
    def send_message(session_id: str, body: MessageRequest, user: ReadyUser) -> TurnReply:
        own_session(session_id, user)
        started = time.perf_counter()
        result = run(
            lambda: tutor.reply(session_id, body.text.strip(), body.alternatives, body.typed)
        )
        logger.info("Partnerin cevabı %.1f sn sürdü.", time.perf_counter() - started)
        return TurnReply.from_result(result)

    @app.post("/api/sessions/{session_id}/end")
    def end_session(session_id: str, user: ReadyUser) -> EndReply:
        own_session(session_id, user)
        result = run(lambda: tutor.end(session_id))
        if result.report is None:
            raise HTTPException(500, "Konuşma özeti hazırlanamadı.")
        return EndReply(**TurnReply.from_result(result).model_dump(), report=result.report)

    # Konuşma kaydı ham ses olarak gelir, yazıya çevrilir ve bırakılır; hiçbir yere kaydedilmez.
    @app.post("/api/speech/transcribe")
    async def transcribe(request: Request, user: User) -> TranscriptOut:
        if transcriber is None:
            raise HTTPException(503, "Sunucuda konuşma tanıma açık değil.")
        audio = await request.body()
        if not audio:
            raise HTTPException(400, "Ses kaydı boş geldi.")
        if len(audio) > MAX_AUDIO_BYTES:
            raise HTTPException(
                413, "Ses kaydı çok uzun. Daha kısa cümlelerle konuşmayı dener misin?"
            )
        # İpucu iki dilde: yalnızca İngilizce ipucu Türkçe cümleleri İngilizceye çekebiliyor.
        name = user["first_name"]
        hint = (
            f"English conversation practice with {name}. "
            f"{name} bazen Türkçe konuşur: Bunu İngilizce nasıl söylerim?"
        )
        try:
            started = time.perf_counter()
            result = await run_in_threadpool(transcriber.transcribe, audio, hint)
        except Exception as exc:
            raise HTTPException(502, "Sesin yazıya çevrilemedi. Tekrar dener misin?") from exc
        seconds = time.perf_counter() - started
        logger.info("Ses %.1f sn'de yazıya çevrildi (%s).", seconds, result.language)
        return TranscriptOut(text=result.text, language=result.language)

    @app.post("/api/words/explain")
    def explain_word(body: ExplainRequest, user: User) -> ExplainReply:
        word = body.word.strip()
        try:
            explanation = tutor.explain_word(user["id"], word, body.sentence)
        except (CoachOutputError, APIError) as exc:
            raise HTTPException(502, "Kelimenin anlamı şu an getirilemedi.") from exc
        return ExplainReply(word=word, level=tutor.word_level(word), **explanation.model_dump())

    @app.get("/api/me/vocabulary")
    def vocabulary(user: User) -> list[WordItem]:
        # Anlamı eksik kayıtlar tamamlanmaya çalışılır; servis yanıt vermezse liste yine gelir.
        try:
            tutor.fill_meanings(user["id"])
        except APIError:
            logger.warning("Kelime anlamları tamamlanamadı.")
        fields = set(WordItem.model_fields) - {"kind"}
        return [
            WordItem(**{key: row[key] for key in fields}, kind=vocab.kind(row["expression"]))
            for row in tutor.vocabulary(user["id"])
        ]

    # Konuşma dökümünde bir kelimeye dokunarak kaydetme; sonuç gerçek kayıt durumunu söyler.
    @app.post("/api/me/vocabulary")
    def save_word(body: WordRequest, user: User) -> dict[str, bool]:
        return {"saved": tutor.save_word(user["id"], body.expression)}

    # Öğrenci istemediği bir kaydı listesinden çıkarır; başkasının kelimesi bulunamaz (404).
    @app.delete("/api/me/vocabulary/{word_id}", status_code=204)
    def delete_word(word_id: int, user: User) -> None:
        if not tutor.delete_word(user["id"], word_id):
            raise HTTPException(404, "Bu kelime listende bulunamadı.")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # Ana sayfa her istekte sunucuya sorulur; böylece güncellemeler hemen görünür.
    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/static", FreshStaticFiles(directory=WEB_DIR), name="static")
    return app


# Gerçek uygulama: ayarları okur; Claude'u, veritabanını, e-postayı ve kelime listesini bağlar.
def build_default_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
    settings = load_settings()
    db = Database(settings.database_path)
    llm = AnthropicClient(model=settings.coach_model, api_key=settings.anthropic_api_key)
    words = wordlist.load()
    tutor = Tutor(Coach(llm), db, LexicalProfile.from_entries(words), plan=LearningPlan(words))

    mailer = ConsoleMailer()
    if settings.smtp_host and settings.smtp_user and settings.smtp_password:
        mailer = SmtpMailer(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_user,
            settings.smtp_password,
            settings.mail_from or settings.smtp_user,
        )
    accounts = Accounts(db, mailer, settings.app_url)

    # Whisper kuruluysa ve kapatılmadıysa konuşma sunucuda tanınır; yoksa tarayıcı tanır.
    transcriber = None
    if settings.whisper_model != "off" and whisper_installed():
        transcriber = WhisperTranscriber(settings.whisper_model)
        transcriber.warm_up()
    return create_app(tutor, accounts, settings.cookie_secure, transcriber)
