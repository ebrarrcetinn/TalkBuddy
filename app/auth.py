# Hesap güvenliği: şifre özeti, oturum ve sıfırlama anahtarları, form kontrolleri, e-posta.
import hashlib
import hmac
import logging
import re
import secrets
import smtplib
from email.message import EmailMessage
from typing import Protocol

logger = logging.getLogger("talkbuddy")

# scrypt, şifreyi geri çevrilemez ve yavaş hesaplanan bir özete dönüştürür.
SCRYPT = {"n": 2**14, "r": 8, "p": 1}
MIN_PASSWORD_LENGTH = 8
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, expected = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **SCRYPT)
    return hmac.compare_digest(digest.hex(), expected)


# Anahtarın kendisi kullanıcıya verilir; veritabanında yalnızca özeti saklanır.
def new_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, token_hash(token)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def password_errors(password: str, confirm: str) -> dict[str, str]:
    errors = {}
    if not password:
        errors["password"] = "Şifre zorunludur."
    elif len(password) < MIN_PASSWORD_LENGTH:
        errors["password"] = f"Şifre en az {MIN_PASSWORD_LENGTH} karakter olmalıdır."
    if not confirm:
        errors["password_confirm"] = "Şifre tekrarı zorunludur."
    elif password and confirm != password:
        errors["password_confirm"] = "Şifreler eşleşmiyor."
    return errors


def registration_errors(
    first_name: str, last_name: str, phone: str, email: str, password: str, confirm: str
) -> dict[str, str]:
    errors = {}
    for field, value, label in (
        ("first_name", first_name, "İsim"),
        ("last_name", last_name, "Soyisim"),
        ("phone", phone, "Telefon numarası"),
        ("email", email, "E-posta adresi"),
    ):
        if not value.strip():
            errors[field] = f"{label} zorunludur."

    digits = re.sub(r"\D", "", phone)
    if "phone" not in errors and not 10 <= len(digits) <= 15:
        errors["phone"] = "Geçerli bir telefon numarası girin."
    if "email" not in errors and not EMAIL_PATTERN.match(email.strip()):
        errors["email"] = "Geçerli bir e-posta adresi girin."
    return errors | password_errors(password, confirm)


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


# E-posta servisi tanımlanmamışsa mesaj sunucu terminaline yazılır (yalnızca geliştirme için).
class ConsoleMailer:
    def send(self, to: str, subject: str, body: str) -> None:
        logger.warning("E-posta servisi tanımlı değil. %s adresine gidecek mesaj:\n%s", to, body)


class SmtpMailer:
    def __init__(self, host: str, port: int, user: str, password: str, sender: str):
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._sender = sender

    def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(self._host, self._port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(self._user, self._password)
            smtp.send_message(message)
