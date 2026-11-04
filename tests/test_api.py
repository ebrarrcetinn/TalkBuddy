# Tarayıcının kullandığı API adreslerini sahte bir koçla uçtan uca test eder.
from fastapi.testclient import TestClient

from app.main import create_app
from tests.fakes import FakeLLM, coach_json, make_accounts, make_tutor

FORM = {
    "first_name": "Ebrar",
    "last_name": "Çetin",
    "phone": "05551234567",
    "email": "ebrar@example.com",
    "password": "güvenli-şifre",
    "password_confirm": "güvenli-şifre",
}


def make_client(tmp_path, *outputs: str) -> TestClient:
    tutor = make_tutor(tmp_path, FakeLLM(*outputs))
    return TestClient(create_app(tutor, make_accounts(tmp_path)))


def onboard(client: TestClient, email: str = FORM["email"]) -> None:
    assert client.post("/api/auth/register", json=FORM | {"email": email}).status_code == 201
    client.put("/api/me/age-group", json={"age_group": "21-24"})
    client.put("/api/me/level", json={"level": "B1"})
    client.put("/api/me/interests", json={"interests": ["Seyahat"]})
    client.put("/api/me/goal", json={"goal": "Seyahat"})
    client.put("/api/me/partner", json={"partner": "Male_Coach"})


def test_protected_routes_need_login(tmp_path):
    client = make_client(tmp_path)

    assert client.get("/api/me").status_code == 401
    assert client.post("/api/sessions").status_code == 401


def test_register_errors_are_returned_in_turkish(tmp_path):
    client = make_client(tmp_path)

    response = client.post("/api/auth/register", json=FORM | {"password_confirm": "x"})

    assert response.status_code == 400
    assert response.json()["fields"]["password_confirm"] == "Şifreler eşleşmiyor."


def test_onboarding_then_profile(tmp_path):
    client = make_client(tmp_path)
    onboard(client)

    me = client.get("/api/me").json()

    assert me["first_name"] == "Ebrar"
    assert me["onboarding_step"] == "done"
    assert me["partner"] == "Male_Coach"
    assert me["start_level"] == "B1"
    assert me["level"] == "B1"


def test_conversation_needs_finished_onboarding(tmp_path):
    client = make_client(tmp_path)
    client.post("/api/auth/register", json=FORM)

    assert client.post("/api/sessions").status_code == 409


def test_full_session_flow(tmp_path):
    client = make_client(
        tmp_path,
        coach_json("Hi Ebrar! What did you do yesterday?", CURRENT_LEVEL="B1"),
        coach_json(
            "Just a quick tip: 'I went'. Can you repeat that?",
            CURRENT_LEVEL="B1",
            VOCAB_BOX_UPDATE=[{"expression": "went", "turkish_meaning": "gitti"}],
            ERROR_TRACKING={"latest_error": "I go", "corrected_version": "I went"},
            SESSION_STATE={"phase": "PRACTICE", "awaiting_repetition": True},
            EXPRESSION="happy",
            SPEECH_RATE="slower",
        ),
        coach_json("Here is your summary.", SESSION_STATE={"phase": "SESSION_END"}),
    )
    onboard(client)

    first = client.post("/api/sessions").json()
    session_id = first["session_id"]
    assert first["level"] == "B1"

    reply = client.post(f"/api/sessions/{session_id}/messages", json={"text": "i go school"})
    body = reply.json()
    assert body["awaiting_repetition"] is True
    assert body["correction"]["correction"] == "I went"
    assert body["new_words"] == ["went"]
    assert body["expression"] == "happy"
    assert body["speech_rate"] == "slower"

    end = client.post(f"/api/sessions/{session_id}/end").json()
    assert end["phase"] == "SESSION_END"
    assert end["report"]["turns"] == 1

    [word] = client.get("/api/me/vocabulary").json()
    assert word["expression"] == "went"

    assert client.post("/api/me/vocabulary", json={"expression": "school"}).json() == {
        "saved": True
    }
    assert client.post("/api/me/vocabulary", json={"expression": "School"}).json() == {
        "saved": False
    }
    assert client.get("/api/me").json()["last_topic"] == "Vocabulary Assessment"

    after = client.post(f"/api/sessions/{session_id}/messages", json={"text": "Hi"})
    assert after.status_code == 404


def test_today_chat_resumes_the_open_session(tmp_path):
    client = make_client(
        tmp_path,
        coach_json("Hi! Where are you from?"),
        coach_json("Nice! Bye!", SESSION_STATE={"phase": "SESSION_END"}),
    )
    onboard(client)
    assert client.get("/api/sessions/today").json() == {"open_session": None, "messages": []}

    session_id = client.post("/api/sessions").json()["session_id"]
    today = client.get("/api/sessions/today").json()
    assert today["open_session"]["id"] == session_id
    assert today["messages"] == [{"role": "assistant", "text": "Hi! Where are you from?"}]

    client.post(f"/api/sessions/{session_id}/end")
    after = client.get("/api/sessions/today").json()
    assert after["open_session"] is None
    assert after["messages"][-1] == {"role": "assistant", "text": "Nice! Bye!"}

    client.post("/api/auth/logout")
    onboard(client, email="baska@example.com")
    assert client.get("/api/sessions/today").json()["messages"] == []


def test_users_cannot_reach_each_others_sessions(tmp_path):
    client = make_client(tmp_path, coach_json("Hello!"))
    onboard(client)
    session_id = client.post("/api/sessions").json()["session_id"]

    client.post("/api/auth/logout")
    onboard(client, email="baska@example.com")

    response = client.post(f"/api/sessions/{session_id}/messages", json={"text": "hi"})
    assert response.status_code == 404
    assert client.get("/api/me/vocabulary").json() == []


def test_words_and_patterns_are_listed_apart_and_removable(tmp_path):
    meanings = [
        '{"turkish_meaning": "... bağlı", "example": "It depends on the weather."}',
        '{"turkish_meaning": "okul", "example": "I go to school."}',
    ]
    client = make_client(tmp_path, *meanings)
    onboard(client)
    client.post("/api/me/vocabulary", json={"expression": "school"})
    client.post("/api/me/vocabulary", json={"expression": "It depends on ..."})
    pattern, word = client.get("/api/me/vocabulary").json()
    assert (pattern["kind"], word["kind"]) == ("sentence", "word")
    assert (pattern["turkish_meaning"], word["turkish_meaning"]) == ("... bağlı", "okul")

    client.post("/api/auth/logout")
    onboard(client, email="baska@example.com")
    assert client.delete(f"/api/me/vocabulary/{word['id']}").status_code == 404

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": FORM["email"], "password": FORM["password"]})
    assert client.delete(f"/api/me/vocabulary/{word['id']}").status_code == 204
    assert [w["expression"] for w in client.get("/api/me/vocabulary").json()] == [
        "It depends on ..."
    ]


def test_assessment_endpoints(tmp_path):
    client = make_client(tmp_path)
    client.post("/api/auth/register", json=FORM)
    client.put("/api/me/age-group", json={"age_group": "15-20"})

    state = client.get("/api/assessment").json()
    assert state["level"] == "A1"
    assert len(state["words"]) == 30

    for index in range(5):
        words = client.get("/api/assessment").json()["words"]
        client.post(f"/api/assessment/sections/{index}", json={"selected": words})

    result = client.get("/api/assessment/result").json()
    assert result["recommended_level"] == "C1"
    assert client.get("/api/me").json()["onboarding_step"] == "result"


def test_invalid_model_output_returns_502(tmp_path):
    client = make_client(tmp_path, "bad", "still bad")
    onboard(client)

    response = client.post("/api/sessions")

    assert response.status_code == 502


def test_health_and_index_page(tmp_path):
    client = make_client(tmp_path)

    assert client.get("/api/health").json() == {"status": "ok"}
    page = client.get("/")
    assert "TalkBuddy" in page.text
    assert page.headers["cache-control"] == "no-cache"


# Şifre değişince eski şifre ve diğer cihazlardaki oturumlar geçersiz olur.
def test_change_password(tmp_path):
    client = make_client(tmp_path)
    onboard(client)
    login = {"email": FORM["email"], "password": FORM["password"]}
    other_device = TestClient(client.app)
    other_device.post("/api/auth/login", json=login)

    wrong = client.put(
        "/api/me/password",
        json={
            "current_password": "yanlış",
            "password": "yeni-şifre-1",
            "password_confirm": "yeni-şifre-1",
        },
    )
    assert wrong.json()["fields"]["current_password"] == "Mevcut şifre hatalı."

    changed = client.put(
        "/api/me/password",
        json={
            "current_password": FORM["password"],
            "password": "yeni-şifre-1",
            "password_confirm": "yeni-şifre-1",
        },
    )
    assert changed.status_code == 200
    assert client.get("/api/me").status_code == 200
    assert other_device.get("/api/me").status_code == 401
    assert client.post("/api/auth/login", json=login).status_code == 401


# Geçmiş silinince konuşmalar gider, kelime listesi kalır.
def test_delete_history_keeps_words(tmp_path):
    client = make_client(
        tmp_path,
        coach_json(
            "Hi! Let's learn 'journey'.",
            VOCAB_BOX_UPDATE=[{"expression": "journey", "turkish_meaning": "yolculuk"}],
        ),
    )
    onboard(client)
    session_id = client.post("/api/sessions").json()["session_id"]

    assert client.delete("/api/me/history").status_code == 200

    assert client.post(f"/api/sessions/{session_id}/end").status_code == 404
    assert [w["expression"] for w in client.get("/api/me/vocabulary").json()] == ["journey"]
    assert client.get("/api/me").json()["last_summary"] is None


# Kelime listesi yüklenmemişse değerlendirme kapanır, seviye elle seçilerek devam edilir.
def test_assessment_is_closed_without_word_list(tmp_path):
    tutor = make_tutor(tmp_path, FakeLLM())
    client = TestClient(create_app(tutor, make_accounts(tmp_path, pool={})))
    client.post("/api/auth/register", json=FORM)
    client.put("/api/me/age-group", json={"age_group": "21-24"})

    assert client.get("/api/me").json()["assessment_available"] is False
    assert client.get("/api/assessment").status_code == 503
    assert client.put("/api/me/level", json={"level": "B2"}).status_code == 200


def test_session_topic_must_come_from_the_list(tmp_path):
    client = make_client(tmp_path, coach_json("Let's talk about space!"))
    onboard(client)

    assert client.post("/api/sessions", json={"topic": "Uydurma"}).status_code == 422
    assert client.post("/api/sessions", json={"topic": "Uzay"}).status_code == 200
    assert "Uzay" in client.get("/api/interests").json()


def test_session_length_and_word_explanation(tmp_path):
    client = make_client(
        tmp_path,
        coach_json("Hi!"),
        '{"turkish_meaning": "yolculuk", "example": "The journey was long."}',
    )
    onboard(client)

    assert client.post("/api/sessions", json={"minutes": 7}).status_code == 422
    assert client.post("/api/sessions", json={"minutes": 10}).status_code == 200

    reply = client.post("/api/words/explain", json={"word": "journey", "sentence": "A journey."})
    assert reply.json()["turkish_meaning"] == "yolculuk"
    assert "plan" in client.get("/api/me").json()


def test_email_change_and_review_snooze_endpoints(tmp_path):
    client = make_client(tmp_path)
    onboard(client)

    wrong = client.put("/api/me/email", json={"new_email": "x", "password": FORM["password"]})
    assert wrong.status_code == 400
    ok = client.put(
        "/api/me/email", json={"new_email": "yeni@example.com", "password": FORM["password"]}
    )
    assert ok.status_code == 200
    assert client.post("/api/auth/email/confirm", json={"token": "uydurma"}).status_code == 400

    assert client.post("/api/me/review/snooze").status_code == 200
    assert client.get("/api/me").json()["review_due"] is False


# "Beni hatırla" seçilmezse çerez kalıcı değildir; tarayıcı kapanınca oturum biter.
def test_login_without_remember_sets_a_browser_session_cookie(tmp_path):
    client = make_client(tmp_path)
    client.post("/api/auth/register", json=FORM)
    login = {"email": FORM["email"], "password": FORM["password"]}

    remembered = client.post("/api/auth/login", json=login).headers["set-cookie"]
    session_only = client.post("/api/auth/login", json=login | {"remember": False})

    assert "Max-Age" in remembered
    assert "Max-Age" not in session_only.headers["set-cookie"]


# Yeni akış: amaç ve yaş tek ekranda; ilk öneri başlangıç rotasının ilk dersi.
def test_onboarding_steps_and_first_suggestion(tmp_path):
    client = make_client(
        tmp_path,
        coach_json("Hi Ebrar! How are you?"),
        coach_json("Bu cümle 'Nasılsın?' demek. You can say: I'm fine, thanks."),
    )
    client.post("/api/auth/register", json=FORM)

    client.put("/api/me/age-group", json={"age_group": "21-24"})
    client.put("/api/me/level", json={"level": "A1"})
    assert client.get("/api/me").json()["onboarding_step"] == "interests"
    client.put("/api/me/interests", json={"interests": []})
    assert client.put("/api/me/goal", json={"goal": "x"}).status_code == 400
    client.put("/api/me/goal", json={"goal": "Seyahat"})
    client.put("/api/me/partner", json={"partner": "Female_Coach"})

    me = client.get("/api/me").json()
    assert me["goal"] == "Seyahat"
    assert me["finished_sessions"] == 0
    assert me["suggestion"]["lesson"] == "starter-1"

    assert client.post("/api/sessions", json={"lesson": "uydurma"}).status_code == 422
    started = client.post("/api/sessions", json={"lesson": "starter-1", "minutes": 5})
    session_id = started.json()["session_id"]

    # Türkçe soru düğmesiz, normal bir mesaj olarak gider.
    turkish = client.post(
        f"/api/sessions/{session_id}/messages", json={"text": "Bunu nasıl söylerim?"}
    )
    assert "Nasılsın" in turkish.json()["spoken_text"]


def test_progress_settings_and_notifications(tmp_path):
    client = make_client(
        tmp_path,
        coach_json("Hi!", VOCAB_BOX_UPDATE=["journey"]),
        coach_json("Bye!", SESSION_STATE={"phase": "SESSION_END"}),
    )
    onboard(client)
    session_id = client.post("/api/sessions").json()["session_id"]
    client.post(f"/api/sessions/{session_id}/end")

    progress = client.get("/api/me/progress").json()
    assert progress["sessions"] == 1
    assert progress["streak"] == 1
    assert progress["words_total"] == 1
    first = next(badge for badge in progress["badges"] if badge["key"] == "first-talk")
    assert first["earned"]

    assert client.put("/api/me/settings", json={"daily_goal": 7}).status_code == 422
    me = client.put(
        "/api/me/settings", json={"daily_goal": 5, "notifications": {"weekly": False}}
    ).json()
    assert me["daily_goal"] == 5
    assert me["notification_prefs"]["weekly"] is False
    assert me["notification_prefs"]["daily"] is True

    notes = client.get("/api/me/notifications").json()
    assert notes["unread"] == len(notes["items"]) > 0
    assert "weekly" not in {item["type"] for item in notes["items"]}
    client.post("/api/me/notifications/seen")
    assert client.get("/api/me/notifications").json()["unread"] == 0


def test_static_files_are_revalidated(tmp_path):
    client = make_client(tmp_path)
    response = client.get("/static/js/app.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"


def test_name_change_is_validated(tmp_path):
    client = make_client(tmp_path)
    onboard(client)

    empty = client.put("/api/me/name", json={"first_name": " ", "last_name": "Çetin"})
    assert empty.json()["fields"]["first_name"] == "İsim zorunludur."

    changed = client.put("/api/me/name", json={"first_name": " Cemre ", "last_name": "Çetin"})
    assert changed.json()["first_name"] == "Cemre"


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def test_profile_photo_belongs_to_its_owner(tmp_path):
    client = make_client(tmp_path)
    onboard(client)
    other = TestClient(client.app)
    onboard(other, "diger@example.com")

    assert client.get("/api/me").json()["photo_version"] is None
    saved = client.put("/api/me/photo", content=PNG, headers={"Content-Type": "image/png"})
    assert saved.json()["photo_version"] is not None

    photo = client.get("/api/me/photo")
    assert photo.content == PNG
    assert photo.headers["content-type"] == "image/png"
    assert other.get("/api/me/photo").status_code == 404

    assert client.delete("/api/me/photo").json()["photo_version"] is None
    assert client.get("/api/me/photo").status_code == 404


def test_profile_photo_rejects_other_files(tmp_path):
    client = make_client(tmp_path)
    onboard(client)

    fake = client.put("/api/me/photo", content=b"<svg/>", headers={"Content-Type": "image/png"})
    assert fake.status_code == 400
    svg = client.put("/api/me/photo", content=b"<svg/>", headers={"Content-Type": "image/svg+xml"})
    assert svg.status_code == 400
    big = client.put(
        "/api/me/photo", content=PNG + b"\x00" * 400_000, headers={"Content-Type": "image/png"}
    )
    assert big.status_code == 413
