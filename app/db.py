# SQLite veritabanı: hesaplar, öğrenme profili, oturumlar, kelime kutusu, hatalar ve değerlendirme.
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    age_group TEXT,
    interests TEXT,
    start_level TEXT,
    onboarding_step TEXT NOT NULL DEFAULT 'age',
    goal TEXT,
    daily_goal INTEGER,
    notification_prefs TEXT,
    notifications_seen_at TEXT,
    review_snoozed_until TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users (id),
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS password_resets (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users (id),
    expires_at TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS email_changes (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users (id),
    new_email TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS assessments (
    user_id TEXT PRIMARY KEY REFERENCES users (id),
    sections TEXT NOT NULL,
    selections TEXT NOT NULL,
    current INTEGER NOT NULL DEFAULT 0,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS learners (
    id TEXT PRIMARY KEY,
    persona TEXT NOT NULL,
    level TEXT,
    level_score REAL,
    pending_level TEXT,
    pending_turns INTEGER NOT NULL DEFAULT 0,
    last_topic TEXT,
    next_focus TEXT,
    last_summary TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    learner_id TEXT NOT NULL REFERENCES learners (id),
    persona TEXT NOT NULL,
    start_level TEXT,
    end_level TEXT,
    summary TEXT,
    topic TEXT,
    planned_minutes INTEGER,
    mode TEXT NOT NULL DEFAULT 'practice',
    lesson TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions (id),
    role TEXT NOT NULL,
    content TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vocabulary (
    id INTEGER PRIMARY KEY,
    learner_id TEXT NOT NULL REFERENCES learners (id),
    session_id TEXT REFERENCES sessions (id),
    expression TEXT NOT NULL,
    turkish_meaning TEXT,
    cefr_level TEXT,
    example TEXT,
    status TEXT NOT NULL,
    review_count INTEGER NOT NULL DEFAULT 0,
    next_review TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE (learner_id, expression COLLATE NOCASE)
);

CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY,
    learner_id TEXT NOT NULL REFERENCES learners (id),
    session_id TEXT NOT NULL REFERENCES sessions (id),
    error TEXT NOT NULL,
    correction TEXT NOT NULL,
    focus_area TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS badges (
    user_id TEXT NOT NULL REFERENCES users (id),
    key TEXT NOT NULL,
    earned_at TEXT NOT NULL,
    PRIMARY KEY (user_id, key)
);

CREATE TABLE IF NOT EXISTS photos (
    user_id TEXT PRIMARY KEY REFERENCES users (id),
    content_type TEXT NOT NULL,
    data BLOB NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS weaknesses (
    learner_id TEXT NOT NULL REFERENCES learners (id),
    name TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 1,
    mastered INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (learner_id, name)
);
"""

# Sonradan eklenen sütunlar: tablo → {sütun: tür}. Var olan veritabanları açılırken eklenir.
ADDED_COLUMNS = {
    "users": {
        "review_snoozed_until": "TEXT",
        "goal": "TEXT",
        "daily_goal": "INTEGER",
        "notification_prefs": "TEXT",
        "notifications_seen_at": "TEXT",
    },
    "sessions": {
        "topic": "TEXT",
        "planned_minutes": "INTEGER",
        "mode": "TEXT NOT NULL DEFAULT 'practice'",
        "lesson": "TEXT",
    },
}


class Database:
    def __init__(self, path: str | Path):
        self._path = str(path)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            # Eski veritabanlarına sonradan eklenen sütunlar eklenir; kayıtlar silinmez.
            for table, columns in ADDED_COLUMNS.items():
                existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
                for name, kind in columns.items():
                    if name not in existing:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")

    # Her işlem kendi bağlantısını açar: hata yoksa kaydeder, hata olursa geri alır.
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # Hesap

    def create_user(
        self,
        user_id: str,
        first_name: str,
        last_name: str,
        phone: str,
        email: str,
        password_hash: str,
        now: str,
    ) -> bool:
        with self._connect() as conn:
            inserted = conn.execute(
                "INSERT OR IGNORE INTO users (id, first_name, last_name, phone, email,"
                " password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, first_name, last_name, phone, email, password_hash, now),
            ).rowcount
        return inserted == 1

    def get_user(self, user_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def get_user_by_email(self, email: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    def update_user(self, user_id: str, **fields: str | None) -> None:
        allowed = {
            "first_name",
            "last_name",
            "age_group",
            "interests",
            "start_level",
            "onboarding_step",
            "password_hash",
            "review_snoozed_until",
            "goal",
            "daily_goal",
            "notification_prefs",
            "notifications_seen_at",
        }
        if not fields or not set(fields) <= allowed:
            raise ValueError(f"Unsupported user fields: {sorted(set(fields) - allowed)}")
        columns = ", ".join(f"{name} = ?" for name in fields)
        with self._connect() as conn:
            conn.execute(f"UPDATE users SET {columns} WHERE id = ?", (*fields.values(), user_id))

    def save_auth_token(self, token_hash: str, user_id: str, expires_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO auth_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (token_hash, user_id, expires_at),
            )

    def user_for_token(self, token_hash: str, now: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT users.* FROM auth_tokens JOIN users ON users.id = auth_tokens.user_id"
                " WHERE token_hash = ? AND expires_at > ?",
                (token_hash, now),
            ).fetchone()

    def delete_auth_token(self, token_hash: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM auth_tokens WHERE token_hash = ?", (token_hash,))

    def delete_user_tokens(self, user_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM auth_tokens WHERE user_id = ?", (user_id,))

    def save_reset(self, token_hash: str, user_id: str, expires_at: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO password_resets (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (token_hash, user_id, expires_at),
            )

    # Sıfırlama anahtarı tek kullanımlıktır: geçerliyse kullanıldı olarak işaretlenir.
    def use_reset(self, token_hash: str, now: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id FROM password_resets"
                " WHERE token_hash = ? AND used = 0 AND expires_at > ?",
                (token_hash, now),
            ).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE password_resets SET used = 1 WHERE token_hash = ?", (token_hash,))
            return row["user_id"]

    def save_email_change(
        self, token_hash: str, user_id: str, new_email: str, expires_at: str
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO email_changes (token_hash, user_id, new_email, expires_at)"
                " VALUES (?, ?, ?, ?)",
                (token_hash, user_id, new_email, expires_at),
            )

    # Onay bağlantısı tek kullanımlıktır. Adres bu arada başka hesapta kullanılmışsa False döner.
    def use_email_change(self, token_hash: str, now: str) -> bool | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_id, new_email FROM email_changes"
                " WHERE token_hash = ? AND used = 0 AND expires_at > ?",
                (token_hash, now),
            ).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE email_changes SET used = 1 WHERE token_hash = ?", (token_hash,))
            email, user_id = row["new_email"], row["user_id"]
            taken = conn.execute(
                "SELECT 1 FROM users WHERE email = ? AND id != ?", (email, user_id)
            ).fetchone()
            if taken:
                return False
            conn.execute("UPDATE users SET email = ? WHERE id = ?", (email, user_id))
            return True

    # Başlangıç değerlendirmesi

    def get_assessment(self, user_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM assessments WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        return {
            "sections": json.loads(row["sections"]),
            "selections": json.loads(row["selections"]),
            "current": row["current"],
            "completed_at": row["completed_at"],
        }

    def save_assessment(
        self,
        user_id: str,
        sections: list[list[str]],
        selections: list[list[str]],
        current: int,
        completed_at: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO assessments (user_id, sections, selections, current, completed_at)"
                " VALUES (?, ?, ?, ?, ?) ON CONFLICT (user_id) DO UPDATE SET"
                " sections = excluded.sections, selections = excluded.selections,"
                " current = excluded.current, completed_at = excluded.completed_at",
                (user_id, json.dumps(sections), json.dumps(selections), current, completed_at),
            )

    # Öğrenci

    def count_sessions(self, learner_id: str) -> int:
        with self._connect() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE learner_id = ?", (learner_id,)
            ).fetchone()[0]

    def get_learner(self, learner_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM learners WHERE id = ?", (learner_id,)).fetchone()

    def save_learner(self, learner_id: str, persona: str, now: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO learners (id, persona, created_at) VALUES (?, ?, ?)"
                " ON CONFLICT (id) DO UPDATE SET persona = excluded.persona",
                (learner_id, persona, now),
            )

    def set_persona(self, learner_id: str, persona: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE learners SET persona = ? WHERE id = ?", (persona, learner_id))

    def save_level(
        self,
        learner_id: str,
        level: str | None,
        score: float | None,
        pending: str | None,
        turns: int,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE learners SET level = ?, level_score = ?, pending_level = ?,"
                " pending_turns = ? WHERE id = ?",
                (level, score, pending, turns, learner_id),
            )

    # Boş gelen değerler eskisinin üzerine yazılmaz.
    # Konuşma geçmişi silinir; kelime listesi ve seviye korunur.
    def delete_history(self, learner_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE vocabulary SET session_id = NULL WHERE learner_id = ?", (learner_id,)
            )
            conn.execute("DELETE FROM errors WHERE learner_id = ?", (learner_id,))
            conn.execute(
                "DELETE FROM messages WHERE session_id IN"
                " (SELECT id FROM sessions WHERE learner_id = ?)",
                (learner_id,),
            )
            conn.execute("DELETE FROM sessions WHERE learner_id = ?", (learner_id,))
            conn.execute(
                "UPDATE learners SET last_topic = NULL, last_summary = NULL WHERE id = ?",
                (learner_id,),
            )

    def save_notes(
        self,
        learner_id: str,
        last_topic: str | None = None,
        next_focus: str | None = None,
        last_summary: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE learners SET last_topic = COALESCE(?, last_topic),"
                " next_focus = COALESCE(?, next_focus), last_summary = COALESCE(?, last_summary)"
                " WHERE id = ?",
                (last_topic, next_focus, last_summary, learner_id),
            )

    # Oturum ve mesajlar

    def create_session(
        self,
        session_id: str,
        learner_id: str,
        persona: str,
        start_level: str | None,
        now: str,
        topic: str | None = None,
        planned_minutes: int | None = None,
        mode: str = "practice",
        lesson: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO sessions (id, learner_id, persona, start_level, topic,"
                " planned_minutes, mode, lesson, started_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    learner_id,
                    persona,
                    start_level,
                    topic,
                    planned_minutes,
                    mode,
                    lesson,
                    now,
                ),
            )

    # Bitirilmiş konuşmalar: başlangıç rotasında hangi derslerin tamamlandığı buradan çıkar.
    def finished_sessions(self, learner_id: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM sessions WHERE learner_id = ? AND ended_at IS NOT NULL"
                " ORDER BY ended_at",
                (learner_id,),
            ).fetchall()

    # En son tamamlanan aylık değerlendirmenin bitiş zamanı.
    def last_review(self, learner_id: str) -> str | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT MAX(ended_at) FROM sessions"
                " WHERE learner_id = ? AND mode = 'monthly' AND ended_at IS NOT NULL",
                (learner_id,),
            ).fetchone()[0]

    # Belirli bir andan sonra başlayan konuşmalar (ör. bugünün sohbeti), başlangıç sırasıyla.
    def sessions_since(self, learner_id: str, since: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM sessions WHERE learner_id = ? AND started_at >= ?"
                " ORDER BY started_at",
                (learner_id, since),
            ).fetchall()

    def get_session(self, session_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()

    def end_session(self, session_id: str, end_level: str | None, summary: str, now: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET end_level = ?, summary = ?, ended_at = ? WHERE id = ?",
                (end_level, summary, now, session_id),
            )

    def add_messages(self, session_id: str, messages: list[dict[str, str]]) -> None:
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                [(session_id, m["role"], m["content"]) for m in messages],
            )

    def get_messages(self, session_id: str) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    # Kelime kutusu

    def get_word(self, learner_id: str, expression: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM vocabulary WHERE learner_id = ? AND expression = ? COLLATE NOCASE",
                (learner_id, expression),
            ).fetchone()

    def add_word(
        self,
        learner_id: str,
        session_id: str | None,
        expression: str,
        turkish_meaning: str | None,
        cefr_level: str | None,
        example: str | None,
        status: str,
        next_review: str,
        now: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO vocabulary (learner_id, session_id, expression, turkish_meaning,"
                " cefr_level, example, status, next_review, added_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    learner_id,
                    session_id,
                    expression,
                    turkish_meaning,
                    cefr_level,
                    example,
                    status,
                    next_review,
                    now,
                ),
            )

    # Kayıtlı kelimede eksik bilgileri tamamlar; var olanlara dokunmaz.
    def fill_word(
        self, word_id: int, turkish_meaning: str | None, cefr_level: str | None, example: str | None
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE vocabulary SET turkish_meaning = COALESCE(turkish_meaning, ?),"
                " cefr_level = COALESCE(cefr_level, ?), example = COALESCE(example, ?)"
                " WHERE id = ?",
                (turkish_meaning, cefr_level, example, word_id),
            )

    def save_review(self, word_id: int, review_count: int, status: str, next_review: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE vocabulary SET review_count = ?, status = ?, next_review = ? WHERE id = ?",
                (review_count, status, next_review, word_id),
            )

    def due_words(self, learner_id: str, today: str, limit: int = 5) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT expression FROM vocabulary WHERE learner_id = ? AND next_review <= ?"
                " AND status != 'MASTERED' ORDER BY next_review LIMIT ?",
                (learner_id, today, limit),
            ).fetchall()
        return [row["expression"] for row in rows]

    def list_words(self, learner_id: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM vocabulary WHERE learner_id = ? ORDER BY added_at DESC, id DESC",
                (learner_id,),
            ).fetchall()

    # Yalnızca öğrencinin kendi kelimesi silinir; silindiyse True döner.
    def delete_word(self, learner_id: str, word_id: int) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM vocabulary WHERE id = ? AND learner_id = ?", (word_id, learner_id)
            )
        return cursor.rowcount > 0

    def session_words(self, session_id: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM vocabulary WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()

    # Hatalar ve zayıf konular

    def add_error(
        self,
        learner_id: str,
        session_id: str,
        error: str,
        correction: str,
        focus_area: str | None,
        now: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO errors (learner_id, session_id, error, correction, focus_area,"
                " created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (learner_id, session_id, error, correction, focus_area, now),
            )

    def session_errors(self, session_id: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM errors WHERE session_id = ? ORDER BY id", (session_id,)
            ).fetchall()

    def recent_errors(self, learner_id: str, limit: int = 3) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM errors WHERE learner_id = ? ORDER BY id DESC LIMIT ?",
                (learner_id, limit),
            ).fetchall()

    def bump_weakness(self, learner_id: str, name: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO weaknesses (learner_id, name) VALUES (?, ?)"
                " ON CONFLICT (learner_id, name) DO UPDATE SET count = count + 1, mastered = 0",
                (learner_id, name),
            )

    def master_weakness(self, learner_id: str, name: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE weaknesses SET mastered = 1 WHERE learner_id = ? AND name = ?",
                (learner_id, name),
            )

    # Rozet bir kez kazanılır; kazanıldığı an saklanır (bildirim tarihi buradan gelir).
    def add_badges(self, user_id: str, keys: set[str], now: str) -> None:
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO badges (user_id, key, earned_at) VALUES (?, ?, ?)",
                [(user_id, key, now) for key in sorted(keys)],
            )

    def save_photo(self, user_id: str, content_type: str, data: bytes, now: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO photos (user_id, content_type, data, updated_at) VALUES (?, ?, ?, ?)"
                " ON CONFLICT (user_id) DO UPDATE SET content_type = excluded.content_type,"
                " data = excluded.data, updated_at = excluded.updated_at",
                (user_id, content_type, data, now),
            )

    def photo(self, user_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT content_type, data, updated_at FROM photos WHERE user_id = ?", (user_id,)
            ).fetchone()

    def delete_photo(self, user_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM photos WHERE user_id = ?", (user_id,))

    def badges(self, user_id: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT key, earned_at FROM badges WHERE user_id = ? ORDER BY earned_at", (user_id,)
            ).fetchall()

    def top_weaknesses(self, learner_id: str, limit: int = 3) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT name, count FROM weaknesses WHERE learner_id = ? AND mastered = 0"
                " ORDER BY count DESC, name LIMIT ?",
                (learner_id, limit),
            ).fetchall()
