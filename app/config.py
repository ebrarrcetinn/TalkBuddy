# Uygulama ayarlarını ortam değişkenlerinden (.env) okur.
import os
from dataclasses import dataclass


# Ayarları tek pakette taşır; frozen=True ile okunduktan sonra değiştirilemez.
@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    coach_model: str
    database_path: str
    app_url: str
    cookie_secure: bool
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_password: str | None
    mail_from: str | None
    whisper_model: str


def load_settings() -> Settings:
    # Anahtarı oku; satır yoksa boş metin say, baştaki/sondaki boşlukları temizle.
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()

    # Anahtar boşsa uygulama daha açılırken net bir mesajla durur.
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is empty. Add your key to the .env file.")

    # SMTP ayarları yoksa şifre sıfırlama bağlantısı sunucu terminaline yazılır.
    return Settings(
        anthropic_api_key=api_key,
        coach_model=os.getenv("COACH_MODEL", "claude-sonnet-5-5"),
        database_path=os.getenv("DATABASE_PATH", "talkbuddy.db"),
        app_url=os.getenv("APP_URL", "http://localhost:8080"),
        cookie_secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        smtp_host=os.getenv("SMTP_HOST") or None,
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER") or None,
        smtp_password=os.getenv("SMTP_PASSWORD") or None,
        mail_from=os.getenv("MAIL_FROM") or None,
        # Konuşma tanıma modeli: tiny, base, small, medium. "off" yazılırsa tarayıcının
        # kendi tanıması kullanılır.
        whisper_model=os.getenv("WHISPER_MODEL", "small").strip() or "small",
    )
