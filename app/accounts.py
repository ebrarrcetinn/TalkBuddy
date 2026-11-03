# Hesap ve ilk kurulum akışı: kayıt, giriş, şifre sıfırlama, partner, yaş grubu ve seviye.
import random
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app import assessment, auth, wordlist
from app.auth import Mailer
from app.db import Database
from app.level import LEVELS, to_score
from app.schemas import Persona

SESSION_DAYS = 30
RESET_HOURS = 1
EMAIL_CHANGE_HOURS = 24
# Aylık konuşma değerlendirmesi yaklaşık 30 günde bir önerilir; "sonra" denirse 7 gün ertelenir.
REVIEW_DAYS = 30
REVIEW_SNOOZE_DAYS = 7

AGE_GROUPS = ["0-6", "7-14", "15-20", "21-24", "25-30", "31-35", "36+"]

# İlgi alanları: kurulumda, profilde ve konu seçiminde aynı liste kullanılır.
INTERESTS = [
    "Günlük hayat",
    "Seyahat",
    "Yemek ve mutfak",
    "Spor",
    "Sağlık ve fitness",
    "Müzik",
    "Film ve dizi",
    "Kitaplar",
    "Oyunlar",
    "Teknoloji",
    "Yapay zekâ",
    "Bilim",
    "Uzay",
    "Doğa ve hayvanlar",
    "Çevre",
    "Tarih",
    "Sanat ve tasarım",
    "Fotoğrafçılık",
    "Moda",
    "İş hayatı ve kariyer",
    "İş görüşmesi",
    "Eğitim ve okul",
    "Aile ve arkadaşlar",
    "Kültür ve gelenekler",
    "Alışveriş",
    "Haberler ve güncel olaylar",
]
MAX_INTERESTS = 10

# İngilizce öğrenme amacı; partner konuşmaları bu amaca göre de kişiselleştirir.
GOALS = [
    "Günlük konuşma",
    "Seyahat",
    "İş ve kariyer",
    "Okul ve eğitim",
    "Yurt dışında yaşamak",
    "Kendimi geliştirmek",
]

# İlk kurulum adımları sırasıyla: yaş → seviye → (değerlendirme → sonuç) → ilgi alanları → amaç
# → partner → bitti. Yarıda bırakan kullanıcı kaldığı adımdan devam eder.
AGE, LEVEL, ASSESSMENT, RESULT, INTERESTS_STEP, GOAL_STEP, PARTNER, DONE = (
    "age",
    "level",
    "assessment",
    "result",
    "interests",
    "goal",
    "partner",
    "done",
)
DEFAULT_PARTNER = Persona.FEMALE
NAME_MAX_LENGTH = 50

# Profil fotoğrafı tarayıcıda küçültülüp gönderilir; sunucu yine de türü ve boyutu denetler.
PHOTO_MAX_BYTES = 300_000
PHOTO_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


class AccountError(Exception):
    def __init__(self, message: str, fields: dict[str, str] | None = None, status: int = 400):
        super().__init__(message)
        self.message = message
        self.fields = fields or {}
        self.status = status


class Accounts:
    def __init__(
        self,
        db: Database,
        mailer: Mailer,
        app_url: str,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        rng: random.Random | None = None,
        pool: dict[str, list[wordlist.Entry]] | None = None,
    ):
        self._db = db
        self._mailer = mailer
        self._app_url = app_url.rstrip("/")
        self._clock = clock
        self._rng = rng or random.SystemRandom()
        self._pool = assessment.build_pool(wordlist.load()) if pool is None else pool

    # Kayıt ve giriş

    def register(
        self, first_name: str, last_name: str, phone: str, email: str, password: str, confirm: str
    ) -> str:
        errors = auth.registration_errors(first_name, last_name, phone, email, password, confirm)
        if errors:
            raise AccountError("Lütfen formdaki hataları düzeltin.", errors)

        user_id = uuid.uuid4().hex
        created = self._db.create_user(
            user_id,
            first_name.strip(),
            last_name.strip(),
            phone.strip(),
            auth.normalize_email(email),
            auth.hash_password(password),
            self._now(),
        )
        if not created:
            message = "Bu e-posta adresiyle zaten bir hesap var."
            raise AccountError(message, {"email": message}, status=409)
        # Öğrenme profili kayıtla birlikte açılır; partner seçilince güncellenir.
        self._db.save_learner(user_id, DEFAULT_PARTNER, self._now())
        return self._issue_token(user_id)

    def login(self, email: str, password: str) -> str:
        user = self._db.get_user_by_email(auth.normalize_email(email))
        if user is None or not auth.verify_password(password, user["password_hash"]):
            raise AccountError("E-posta veya şifre hatalı.", status=401)
        return self._issue_token(user["id"])

    def logout(self, token: str) -> None:
        self._db.delete_auth_token(auth.token_hash(token))

    def user(self, user_id: str):
        return self._db.get_user(user_id)

    def user_for_token(self, token: str):
        return self._db.user_for_token(auth.token_hash(token), self._now())

    # Kayıtlı olmayan e-posta için de aynı cevap verilir; böylece hangi adreslerin kayıtlı
    # olduğu dışarıdan öğrenilemez.
    def request_password_reset(self, email: str) -> None:
        user = self._db.get_user_by_email(auth.normalize_email(email))
        if user is None:
            return
        token, digest = auth.new_token()
        expires = self._clock() + timedelta(hours=RESET_HOURS)
        self._db.save_reset(digest, user["id"], expires.isoformat())
        self._mailer.send(
            user["email"],
            "TalkBuddy şifre sıfırlama",
            f"Merhaba {user['first_name']},\n\n"
            f"Şifreni sıfırlamak için bu bağlantıyı aç:\n{self._app_url}/?reset={token}\n\n"
            f"Bağlantı {RESET_HOURS} saat geçerlidir. Bu isteği sen yapmadıysan bu e-postayı "
            "görmezden gelebilirsin.",
        )

    def reset_password(self, token: str, password: str, confirm: str) -> None:
        errors = auth.password_errors(password, confirm)
        if errors:
            raise AccountError("Lütfen formdaki hataları düzeltin.", errors)
        user_id = self._db.use_reset(auth.token_hash(token), self._now())
        if user_id is None:
            raise AccountError("Bu bağlantı geçersiz ya da süresi dolmuş.")
        self._db.update_user(user_id, password_hash=auth.hash_password(password))
        self._db.delete_user_tokens(user_id)

    # Şifre değişince bütün açık oturumlar kapanır, bu cihaz için yeni oturum açılır.
    def change_password(self, user_id: str, current: str, password: str, confirm: str) -> str:
        user = self._db.get_user(user_id)
        errors = auth.password_errors(password, confirm)
        if not auth.verify_password(current, user["password_hash"]):
            errors["current_password"] = "Mevcut şifre hatalı."
        if errors:
            raise AccountError("Lütfen formdaki hataları düzeltin.", errors)
        self._db.update_user(user_id, password_hash=auth.hash_password(password))
        self._db.delete_user_tokens(user_id)
        return self._issue_token(user_id)

    def set_name(self, user_id: str, first_name: str, last_name: str) -> None:
        errors = {}
        for field, value, label in (
            ("first_name", first_name, "İsim"),
            ("last_name", last_name, "Soyisim"),
        ):
            if not value.strip():
                errors[field] = f"{label} zorunludur."
            elif len(value.strip()) > NAME_MAX_LENGTH:
                errors[field] = f"{label} en fazla {NAME_MAX_LENGTH} karakter olabilir."
        if errors:
            raise AccountError("Lütfen formdaki hataları düzeltin.", errors)
        self._db.update_user(user_id, first_name=first_name.strip(), last_name=last_name.strip())

    def save_photo(self, user_id: str, content_type: str, data: bytes) -> None:
        signatures = PHOTO_SIGNATURES.get(content_type)
        if signatures is None or not data.startswith(signatures):
            raise AccountError("Fotoğraf JPEG, PNG ya da WebP olmalı.")
        if content_type == "image/webp" and data[8:12] != b"WEBP":
            raise AccountError("Fotoğraf JPEG, PNG ya da WebP olmalı.")
        if len(data) > PHOTO_MAX_BYTES:
            raise AccountError("Fotoğraf çok büyük. Daha küçük bir fotoğraf seç.")
        self._db.save_photo(user_id, content_type, data, self._now())

    def photo(self, user_id: str):
        return self._db.photo(user_id)

    def delete_photo(self, user_id: str) -> None:
        self._db.delete_photo(user_id)

    def delete_history(self, user_id: str) -> None:
        self._db.delete_history(user_id)

    # E-posta değişikliği: yeni adrese onay bağlantısı gider, adres ancak onaylanınca değişir.
    def request_email_change(self, user_id: str, new_email: str, password: str) -> None:
        user = self._db.get_user(user_id)
        email = auth.normalize_email(new_email)
        errors = {}
        if not auth.EMAIL_PATTERN.match(email):
            errors["new_email"] = "Geçerli bir e-posta adresi girin."
        elif email == user["email"]:
            errors["new_email"] = "Bu zaten şu anki e-posta adresin."
        elif self._db.get_user_by_email(email) is not None:
            errors["new_email"] = "Bu e-posta adresiyle başka bir hesap var."
        if not auth.verify_password(password, user["password_hash"]):
            errors["password"] = "Şifre hatalı."
        if errors:
            raise AccountError("Lütfen formdaki hataları düzeltin.", errors)

        token, digest = auth.new_token()
        expires = self._clock() + timedelta(hours=EMAIL_CHANGE_HOURS)
        self._db.save_email_change(digest, user_id, email, expires.isoformat())
        self._mailer.send(
            email,
            "TalkBuddy e-posta adresi onayı",
            f"Merhaba {user['first_name']},\n\n"
            "E-posta adresini değiştirmek için bu bağlantıyı aç:\n"
            f"{self._app_url}/?email={token}\n\n"
            f"Bağlantı {EMAIL_CHANGE_HOURS} saat geçerlidir. "
            "Bu isteği sen yapmadıysan bu e-postayı görmezden gelebilirsin.",
        )

    def confirm_email_change(self, token: str) -> None:
        result = self._db.use_email_change(auth.token_hash(token), self._now())
        if result is None:
            raise AccountError("Bu bağlantı geçersiz ya da süresi dolmuş.")
        if result is False:
            raise AccountError("Bu e-posta adresi başka bir hesapta kullanılıyor.", status=409)

    # Aylık değerlendirme: son değerlendirmeden (yoksa kayıttan) bu yana 30 gün geçtiyse önerilir.
    def review_due(self, user_id: str) -> bool:
        user = self._db.get_user(user_id)
        if user["onboarding_step"] != DONE:
            return False
        now = self._clock()
        snoozed = user["review_snoozed_until"]
        if snoozed and datetime.fromisoformat(snoozed) > now:
            return False
        since = datetime.fromisoformat(self._db.last_review(user_id) or user["created_at"])
        return now - since >= timedelta(days=REVIEW_DAYS)

    def snooze_review(self, user_id: str) -> None:
        until = self._clock() + timedelta(days=REVIEW_SNOOZE_DAYS)
        self._db.update_user(user_id, review_snoozed_until=until.isoformat())

    # İlk kurulum ve profil tercihleri

    def set_age_group(self, user_id: str, age_group: str) -> None:
        if age_group not in AGE_GROUPS:
            raise AccountError("Geçerli bir yaş grubu seçin.")
        user = self._db.get_user(user_id)
        step = LEVEL if user["onboarding_step"] == AGE else user["onboarding_step"]
        self._db.update_user(user_id, age_group=age_group, onboarding_step=step)

    def set_goal(self, user_id: str, goal: str) -> None:
        if goal not in GOALS:
            raise AccountError("Bir öğrenme amacı seç.")
        user = self._db.get_user(user_id)
        fields = {"goal": goal}
        if user["onboarding_step"] == GOAL_STEP:
            fields["onboarding_step"] = PARTNER
        self._db.update_user(user_id, **fields)

    # Seviye doğrudan seçilir ya da değerlendirme sonucundan sonra onaylanır.
    # İlk seçilen seviye "başlangıç seviyesi" olarak ayrıca saklanır.
    def set_level(self, user_id: str, level: str) -> None:
        if level not in LEVELS:
            raise AccountError("Geçerli bir seviye seçin.")
        user = self._db.get_user(user_id)
        self._require_step(
            user, {LEVEL, ASSESSMENT, RESULT, INTERESTS_STEP, GOAL_STEP, PARTNER, DONE}
        )
        fields = {}
        if user["start_level"] is None:
            fields["start_level"] = level
        if user["onboarding_step"] in {LEVEL, ASSESSMENT, RESULT}:
            fields["onboarding_step"] = INTERESTS_STEP
        if fields:
            self._db.update_user(user_id, **fields)
        self._db.save_level(user_id, level, to_score(level), None, 0)

    # Partner kurulumun son adımıdır; sonradan profilden değiştirilebilir.
    def set_partner(self, user_id: str, partner: Persona) -> None:
        user = self._db.get_user(user_id)
        self._require_step(user, {PARTNER, DONE})
        self._db.set_persona(user_id, partner)
        if user["onboarding_step"] == PARTNER:
            self._db.update_user(user_id, onboarding_step=DONE)

    # İlgi alanları listeden seçilir; boş bırakılabilir. Kurulumdaysa amaç adımına geçilir.
    def set_interests(self, user_id: str, interests: list[str]) -> None:
        user = self._db.get_user(user_id)
        self._require_step(user, {INTERESTS_STEP, GOAL_STEP, PARTNER, DONE})
        chosen = list(dict.fromkeys(item for item in interests if item in INTERESTS))
        if len(chosen) != len(set(interests)):
            raise AccountError("Listede olmayan bir ilgi alanı seçildi.")
        if len(chosen) > MAX_INTERESTS:
            raise AccountError(f"En fazla {MAX_INTERESTS} ilgi alanı seçebilirsin.")
        fields = {"interests": ", ".join(chosen) or None}
        if user["onboarding_step"] == INTERESTS_STEP:
            fields["onboarding_step"] = GOAL_STEP
        self._db.update_user(user_id, **fields)

    # Başlangıç değerlendirmesi

    # Kelime listesi yüklü değilse değerlendirme kapalıdır; kullanıcı seviyesini kendisi seçer.
    def assessment_available(self) -> bool:
        return assessment.is_ready(self._pool)

    def assessment_state(self, user_id: str) -> dict:
        user = self._db.get_user(user_id)
        self._require_step(user, {LEVEL, ASSESSMENT, RESULT})
        state = self._db.get_assessment(user_id)
        if state is None:
            if not self.assessment_available():
                raise AccountError(
                    "Kelime değerlendirmesi şu an kullanılamıyor. Seviyeni listeden seçebilirsin.",
                    status=503,
                )
            sections = assessment.build_sections(self._pool, self._rng)
            state = {"sections": sections, "selections": [], "current": 0, "completed_at": None}
            self._db.save_assessment(user_id, sections, [], 0)
        if user["onboarding_step"] == LEVEL:
            self._db.update_user(user_id, onboarding_step=ASSESSMENT)
        return state

    def submit_section(self, user_id: str, index: int, selected: list[str]) -> dict:
        state = self.assessment_state(user_id)
        # Yalnızca sıradaki bölüm kabul edilir; aynı bölüm iki kez gönderilirse yok sayılır.
        if state["completed_at"] or index != state["current"]:
            return state
        words = state["sections"][index]
        chosen = [word for word in words if word in set(selected)]
        selections = [*state["selections"], chosen]
        current = index + 1
        completed = self._now() if current == len(assessment.LEVELS) else None
        self._db.save_assessment(user_id, state["sections"], selections, current, completed)
        if completed:
            self._db.update_user(user_id, onboarding_step=RESULT)
        return self._db.get_assessment(user_id)

    def assessment_result(self, user_id: str) -> assessment.AssessmentResult:
        state = self._db.get_assessment(user_id)
        if state is None or state["completed_at"] is None:
            raise AccountError("Değerlendirme henüz tamamlanmadı.", status=409)
        return assessment.evaluate(state["selections"])

    def _require_step(self, user, allowed: set[str]) -> None:
        if user["onboarding_step"] not in allowed:
            raise AccountError("Önce önceki kurulum adımlarını tamamla.", status=409)

    def _issue_token(self, user_id: str) -> str:
        token, digest = auth.new_token()
        expires = self._clock() + timedelta(days=SESSION_DAYS)
        self._db.save_auth_token(digest, user_id, expires.isoformat())
        return token

    def _now(self) -> str:
        return self._clock().isoformat()
