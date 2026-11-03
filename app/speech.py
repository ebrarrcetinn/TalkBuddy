# Konuşmayı yazıya çevirme: tarayıcının kaydettiği ses sunucuda Whisper ile çözülür.
# Ses yalnızca bellekte işlenir, diske yazılmaz ve saklanmaz.
import io
import threading
from dataclasses import dataclass
from importlib.util import find_spec
from typing import Protocol

# Konuşma dili İngilizce ya da Türkçe kabul edilir; başka bir dil algılanırsa İngilizce denenir.
LANGUAGES = {"en", "tr"}


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str


class Transcriber(Protocol):
    def transcribe(self, audio: bytes, hint: str) -> Transcript: ...


def whisper_installed() -> bool:
    return find_spec("faster_whisper") is not None


class WhisperTranscriber:
    # model: hazır yüklenmiş bir model verilebilir (testlerde); verilmezse ilk kullanımda yüklenir.
    def __init__(self, model_size: str = "small", device: str = "auto", model=None):
        self._model_size = model_size
        self._device = device
        self._model = model
        self._lock = threading.Lock()

    # Model ilk kullanımda bir kez yüklenir; ilk seferde internetten indirilir.
    def _load(self):
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self._model_size, device=self._device, compute_type="int8"
                )
        return self._model

    # Sunucu açılırken model arka planda yüklenir; ilk konuşma beklemesin.
    def warm_up(self) -> None:
        threading.Thread(target=self._load, daemon=True).start()

    # hint: Whisper'a verilen kısa bağlam (ör. öğrencinin adı); isimleri doğru yazdırır.
    def transcribe(self, audio: bytes, hint: str) -> Transcript:
        model = self._load()
        text, language = self._run(model, audio, hint, None)
        if language not in LANGUAGES:
            text, language = self._run(model, audio, hint, "en")
        return Transcript(text, language)

    @staticmethod
    def _run(model, audio: bytes, hint: str, language: str | None) -> tuple[str, str]:
        segments, info = model.transcribe(
            io.BytesIO(audio),
            language=language,
            initial_prompt=hint,
            # Kısa konuşma kayıtlarında hızlı mod (beam 1) doğrulukta belirgin fark yaratmaz.
            beam_size=1,
            vad_filter=True,
            without_timestamps=True,
        )
        return " ".join(segment.text.strip() for segment in segments).strip(), info.language
