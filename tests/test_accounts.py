# Kayıt, giriş, şifre sıfırlama ve ilk kurulum akışını test eder.
import pytest

from app.accounts import INTERESTS, AccountError
from app.schemas import Persona
from tests.fakes import FakeClock, FakeMailer, make_accounts

FORM = {
    "first_name": "Ebrar",
    "last_name": "Çetin",
    "phone": "0555 123 45 67",
    "email": "Ebrar@Example.com",
    "password": "güvenli-şifre",
    "confirm": "güvenli-şifre",
}


def register(accounts, **changes) -> str:
    form = FORM | changes
    return accounts.register(*form.values())


def user_id(accounts, token: str) -> str:
    return accounts.user_for_token(token)["id"]


def test_register_and_login(tmp_path):
    accounts = make_accounts(tmp_path)
    token = register(accounts)

    user = accounts.user_for_token(token)
    assert user["email"] == "ebrar@example.com"
    assert user["password_hash"] != FORM["password"]
    assert user["onboarding_step"] == "age"
    assert accounts.user_for_token(accounts.login("EBRAR@example.com", FORM["password"]))


def test_registration_errors_are_turkish(tmp_path):
    accounts = make_accounts(tmp_path)

    with pytest.raises(AccountError) as error:
        register(accounts, first_name="", email="not-an-email", confirm="farkli-sifre")

    assert error.value.fields == {
        "first_name": "İsim zorunludur.",
        "email": "Geçerli bir e-posta adresi girin.",
        "password_confirm": "Şifreler eşleşmiyor.",
    }


def test_duplicate_email_is_rejected(tmp_path):
    accounts = make_accounts(tmp_path)
    register(accounts)

    with pytest.raises(AccountError) as error:
        register(accounts, email="ebrar@example.com")

    assert error.value.status == 409


def test_wrong_password_and_logout(tmp_path):
    accounts = make_accounts(tmp_path)
    token = register(accounts)

    with pytest.raises(AccountError):
        accounts.login(FORM["email"], "yanlış-şifre")

    accounts.logout(token)
    assert accounts.user_for_token(token) is None


def test_password_reset_by_email(tmp_path):
    mailer = FakeMailer()
    accounts = make_accounts(tmp_path, mailer)
    old_token = register(accounts)

    accounts.request_password_reset("nobody@example.com")
    accounts.request_password_reset(FORM["email"])

    [(to, _, body)] = mailer.sent
    assert to == "ebrar@example.com"
    reset_token = body.split("?reset=")[1].split()[0]

    accounts.reset_password(reset_token, "yeni-şifre-123", "yeni-şifre-123")
    assert accounts.user_for_token(old_token) is None
    assert accounts.login(FORM["email"], "yeni-şifre-123")
    with pytest.raises(AccountError):
        accounts.reset_password(reset_token, "baska-sifre-1", "baska-sifre-1")


def test_reset_link_expires(tmp_path):
    mailer, clock = FakeMailer(), FakeClock()
    accounts = make_accounts(tmp_path, mailer, clock)
    register(accounts)
    accounts.request_password_reset(FORM["email"])
    reset_token = mailer.sent[0][2].split("?reset=")[1].split()[0]

    clock.advance(hours=2)

    with pytest.raises(AccountError):
        accounts.reset_password(reset_token, "yeni-şifre-123", "yeni-şifre-123")


def test_onboarding_order_age_level_interests_goal_partner(tmp_path):
    accounts = make_accounts(tmp_path)
    uid = user_id(accounts, register(accounts))

    def step() -> str:
        return accounts.user(uid)["onboarding_step"]

    with pytest.raises(AccountError):
        accounts.set_partner(uid, Persona.MALE)
    with pytest.raises(AccountError):
        accounts.set_interests(uid, ["Seyahat"])

    accounts.set_age_group(uid, "21-24")
    assert step() == "level"
    accounts.set_level(uid, "B1")
    assert step() == "interests"
    accounts.set_interests(uid, ["Seyahat", "Spor"])
    assert step() == "goal"
    with pytest.raises(AccountError):
        accounts.set_partner(uid, Persona.MALE)
    with pytest.raises(AccountError):
        accounts.set_goal(uid, "Uydurma amaç")
    accounts.set_goal(uid, "Seyahat")
    assert step() == "partner"
    accounts.set_partner(uid, Persona.MALE)

    user = accounts.user(uid)
    assert user["onboarding_step"] == "done"
    assert user["start_level"] == "B1"
    assert (user["interests"], user["goal"]) == ("Seyahat, Spor", "Seyahat")


# Geri dönüp seviye ya da yaş değiştiren kullanıcı bulunduğu adımı kaybetmez.
def test_going_back_does_not_move_the_step_backwards(tmp_path):
    accounts = make_accounts(tmp_path)
    uid = user_id(accounts, register(accounts))
    accounts.set_age_group(uid, "21-24")
    accounts.set_level(uid, "A2")
    accounts.set_interests(uid, [])

    accounts.set_level(uid, "B1")
    accounts.set_age_group(uid, "25-30")

    assert accounts.user(uid)["onboarding_step"] == "goal"


def test_start_level_is_kept_when_level_changes(tmp_path):
    accounts = make_accounts(tmp_path)
    uid = user_id(accounts, register(accounts))
    accounts.set_age_group(uid, "25-30")
    accounts.set_level(uid, "A2")
    accounts.set_interests(uid, [])
    accounts.set_goal(uid, "Seyahat")
    accounts.set_partner(uid, Persona.FEMALE)

    accounts.set_level(uid, "B1")

    assert accounts.user(uid)["start_level"] == "A2"


def test_assessment_resumes_and_ignores_double_submit(tmp_path):
    accounts = make_accounts(tmp_path)
    uid = user_id(accounts, register(accounts))
    accounts.set_age_group(uid, "15-20")

    first = accounts.assessment_state(uid)
    words = first["sections"][0]
    accounts.submit_section(uid, 0, words)
    accounts.submit_section(uid, 0, [])

    resumed = accounts.assessment_state(uid)
    assert resumed["sections"] == first["sections"]
    assert resumed["current"] == 1
    assert resumed["selections"] == [words]


def test_assessment_result_then_level_and_partner(tmp_path):
    accounts = make_accounts(tmp_path)
    uid = user_id(accounts, register(accounts))
    accounts.set_age_group(uid, "31-35")
    sections = accounts.assessment_state(uid)["sections"]

    picks = [sections[0], sections[1][:29], sections[2][:28], [], []]
    for index, selected in enumerate(picks):
        accounts.submit_section(uid, index, [*selected, "not-in-section"])

    result = accounts.assessment_result(uid)
    assert result.recommended_level == "A2"
    assert accounts.user(uid)["onboarding_step"] == "result"

    accounts.set_level(uid, result.recommended_level)
    accounts.set_interests(uid, [])
    accounts.set_goal(uid, "Seyahat")
    accounts.set_partner(uid, Persona.FEMALE)
    assert accounts.user(uid)["onboarding_step"] == "done"


# Değerlendirmenin ortasında vazgeçen öğrenci seviyesini kendisi seçebilir.
def test_level_can_be_chosen_during_assessment(tmp_path):
    accounts = make_accounts(tmp_path)
    uid = user_id(accounts, register(accounts))
    accounts.set_age_group(uid, "21-24")
    sections = accounts.assessment_state(uid)["sections"]
    accounts.submit_section(uid, 0, sections[0])

    accounts.set_level(uid, "A2")

    user = accounts.user(uid)
    assert user["onboarding_step"] == "interests"
    assert user["start_level"] == "A2"


# Yaş, değerlendirme kelimelerini etkilemez: aynı rastgelelikle her yaşa aynı bölümler çıkar.
def test_assessment_words_do_not_depend_on_age(tmp_path):
    sections = []
    for age in ["0-6", "36+"]:
        folder = tmp_path / age.replace("+", "plus")
        folder.mkdir()
        accounts = make_accounts(folder)
        uid = user_id(accounts, register(accounts))
        accounts.set_age_group(uid, age)
        sections.append(accounts.assessment_state(uid)["sections"])

    assert sections[0] == sections[1]


# İlgi alanları yalnızca listeden seçilir ve sayısı sınırlıdır; boş bırakmak kurulumu ilerletir.
def test_interests_must_come_from_the_list(tmp_path):
    accounts = make_accounts(tmp_path)
    uid = user_id(accounts, register(accounts))
    accounts.set_age_group(uid, "21-24")
    accounts.set_level(uid, "B1")

    with pytest.raises(AccountError):
        accounts.set_interests(uid, ["Seyahat", "Uydurma konu"])
    with pytest.raises(AccountError):
        accounts.set_interests(uid, INTERESTS[:11])

    accounts.set_interests(uid, [])
    assert accounts.user(uid)["onboarding_step"] == "goal"


# E-posta yalnızca yeni adrese giden bağlantı onaylanınca değişir.
def test_email_change_needs_password_and_confirmation(tmp_path):
    mailer = FakeMailer()
    accounts = make_accounts(tmp_path, mailer=mailer)
    uid = user_id(accounts, register(accounts))

    with pytest.raises(AccountError) as wrong:
        accounts.request_email_change(uid, "yeni@example.com", "yanlış-şifre")
    assert "password" in wrong.value.fields

    accounts.request_email_change(uid, "Yeni@Example.com", FORM["password"])
    to, _, body = mailer.sent[-1]
    assert to == "yeni@example.com"
    assert accounts.user(uid)["email"] == "ebrar@example.com"

    token = body.split("?email=")[1].split()[0]
    accounts.confirm_email_change(token)
    assert accounts.user(uid)["email"] == "yeni@example.com"
    with pytest.raises(AccountError):
        accounts.confirm_email_change(token)


# Aylık değerlendirme 30 gün sonra önerilir, ertelenince bir hafta susar.
def test_monthly_review_is_offered_after_30_days_and_can_be_snoozed(tmp_path):
    clock = FakeClock()
    accounts = make_accounts(tmp_path, clock=clock)
    uid = user_id(accounts, register(accounts))
    accounts.set_age_group(uid, "21-24")
    accounts.set_level(uid, "B1")
    accounts.set_interests(uid, [])
    accounts.set_goal(uid, "Seyahat")
    accounts.set_partner(uid, Persona.FEMALE)

    clock.advance(days=29)
    assert not accounts.review_due(uid)
    clock.advance(days=1)
    assert accounts.review_due(uid)

    accounts.snooze_review(uid)
    assert not accounts.review_due(uid)
    clock.advance(days=7)
    assert accounts.review_due(uid)


def test_existing_users_keep_their_data_when_photos_are_added(tmp_path):
    accounts = make_accounts(tmp_path)
    learner = user_id(accounts, register(accounts))
    accounts.set_name(learner, "Cemre", "Çetin")

    reopened = make_accounts(tmp_path)

    assert reopened.user(learner)["first_name"] == "Cemre"
    assert reopened.photo(learner) is None
