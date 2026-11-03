# Konuşma tanımayı test eder: dil seçimi, uç nokta, boyut sınırı ve kimlik doğrulama.
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import create_app
from app.speech import Transcript, WhisperTranscriber
from tests.fakes import FakeLLM, make_accounts, make_tutor
from tests.test_api import FORM, onboard


# Whisper modelinin yerine geçer: verilen dile göre metin döndürür ve çağrıları kaydeder.
class FakeModel:
    def __init__(self, detected: str):
        self.detected = detected
        self.calls = []

    def transcribe(
        self, audio, language, initial_prompt, beam_size, vad_filter, without_timestamps
    ):
        self.calls.append((language, initial_prompt))
        found = language or self.detected
        return [SimpleNamespace(text=f" text in {found} ")], SimpleNamespace(language=found)


def whisper_with(model: FakeModel) -> WhisperTranscriber:
    return WhisperTranscriber(model=model)


def test_english_and_turkish_are_kept():
    for language in ("en", "tr"):
        model = FakeModel(language)
        result = whisper_with(model).transcribe(b"audio", "hint")
        assert result == Transcript(f"text in {language}", language)
        assert model.calls == [(None, "hint")]


def test_other_languages_fall_back_to_english():
    model = FakeModel("de")

    result = whisper_with(model).transcribe(b"audio", "hint")

    assert result.language == "en"
    assert [language for language, _ in model.calls] == [None, "en"]


class FakeTranscriber:
    def __init__(self):
        self.hints = []

    def transcribe(self, audio: bytes, hint: str) -> Transcript:
        self.hints.append(hint)
        return Transcript("my name is Ebrar", "en")


def client_with(tmp_path, transcriber) -> TestClient:
    tutor = make_tutor(tmp_path, FakeLLM())
    return TestClient(create_app(tutor, make_accounts(tmp_path), transcriber=transcriber))


def test_transcribe_endpoint_uses_the_learner_name(tmp_path):
    transcriber = FakeTranscriber()
    client = client_with(tmp_path, transcriber)
    assert client.post("/api/speech/transcribe", content=b"x").status_code == 401
    onboard(client)

    reply = client.post(
        "/api/speech/transcribe", content=b"audio", headers={"Content-Type": "audio/webm"}
    )

    assert reply.json() == {"text": "my name is Ebrar", "language": "en"}
    assert FORM["first_name"] in transcriber.hints[0]
    assert client.get("/api/me").json()["speech_engine"] == "whisper"


def test_transcribe_rejects_empty_and_too_long_audio(tmp_path):
    client = client_with(tmp_path, FakeTranscriber())
    onboard(client)

    assert client.post("/api/speech/transcribe", content=b"").status_code == 400
    too_long = b"x" * 2_000_001
    assert client.post("/api/speech/transcribe", content=too_long).status_code == 413


def test_without_whisper_the_browser_recognises_speech(tmp_path):
    client = client_with(tmp_path, None)
    onboard(client)

    assert client.get("/api/me").json()["speech_engine"] == "browser"
    assert client.post("/api/speech/transcribe", content=b"audio").status_code == 503
