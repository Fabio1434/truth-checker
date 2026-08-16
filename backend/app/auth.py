import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Optional

DB_PATH = Path(os.getenv("TRUTHCHECKER_DB_PATH", str(Path(__file__).resolve().parents[2] / "truthchecker.db")))
AUTH_SECRET = os.getenv("AUTH_SECRET", "")
if not AUTH_SECRET:
    AUTH_SECRET = secrets.token_urlsafe(48)
    print("[WARNING] AUTH_SECRET is not set. A temporary secret was generated; set AUTH_SECRET in production.")

TOKEN_TTL = int(os.getenv("AUTH_TOKEN_TTL", str(7 * 24 * 3600)))
FREE_DAILY_LIMIT = int(os.getenv("TRUTHCHECKER_DAILY_LIMIT", "1000"))
ENFORCE_DAILY_LIMIT = os.getenv("TRUTHCHECKER_ENFORCE_DAILY_LIMIT", "0").strip().lower() in {"1", "true", "yes", "on"}


def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            daily_limit INTEGER NOT NULL DEFAULT 1000,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL,
            last_login INTEGER
        );
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            content_type TEXT NOT NULL,
            content TEXT,
            verdict TEXT NOT NULL,
            score INTEGER NOT NULL,
            result_json TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_analyses_user_created ON analyses(user_id, created_at DESC);
        """)


def _password_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$16384$8$1$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def _password_verify(password: str, encoded: str) -> bool:
    try:
        _, n, r, p, salt_b64, digest_b64 = encoded.split("$", 5)
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.scrypt(password.encode(), salt=salt, n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def create_user(email: str, password: str):
    email = email.strip().lower()
    now = int(time.time())
    with _db() as db:
        cur = db.execute(
            "INSERT INTO users(email,password_hash,created_at,daily_limit) VALUES(?,?,?,?)",
            (email, _password_hash(password), now, FREE_DAILY_LIMIT),
        )
        user_id = cur.lastrowid
    return get_user(user_id)


def get_user(user_id: int):
    with _db() as db:
        row = db.execute("SELECT * FROM users WHERE id=? AND is_active=1", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_email(email: str):
    with _db() as db:
        row = db.execute("SELECT * FROM users WHERE email=?", (email.strip().lower(),)).fetchone()
        return dict(row) if row else None


def verify_login(email: str, password: str):
    user = get_user_by_email(email)
    if not user or not user["is_active"] or not _password_verify(password, user["password_hash"]):
        return None
    with _db() as db:
        db.execute("UPDATE users SET last_login=? WHERE id=?", (int(time.time()), user["id"]))
    return get_user(user["id"])


def make_token(user_id: int) -> str:
    exp = int(time.time()) + TOKEN_TTL
    payload = f"{user_id}.{exp}"
    sig = hmac.new(AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    return payload + "." + base64.urlsafe_b64encode(sig).decode().rstrip("=")


def verify_token(token: str) -> Optional[dict]:
    try:
        user_id, exp, sig = token.split(".", 2)
        payload = f"{user_id}.{exp}"
        expected = hmac.new(AUTH_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
        if not hmac.compare_digest(expected, supplied) or int(exp) < int(time.time()):
            return None
        return get_user(int(user_id))
    except Exception:
        return None


def usage_today(user_id: int) -> int:
    start = int(time.time() // 86400 * 86400)
    with _db() as db:
        return int(db.execute("SELECT COUNT(*) FROM analyses WHERE user_id=? AND created_at>=?", (user_id, start)).fetchone()[0])


def can_analyze(user: dict) -> bool:
    # The Gemini provider already has its own quotas. Do not add a second
    # application-level quota by default, because it can incorrectly turn a
    # provider error into a generic HTTP 429 for the user.
    if not ENFORCE_DAILY_LIMIT:
        return True
    return usage_today(user["id"]) < int(user.get("daily_limit", FREE_DAILY_LIMIT))


def save_analysis(user_id: int, content_type: str, content: str, result: dict):
    import json
    with _db() as db:
        db.execute(
            "INSERT INTO analyses(user_id,content_type,content,verdict,score,result_json,created_at) VALUES(?,?,?,?,?,?,?)",
            (user_id, content_type, content[:10000], result.get("verdict", "non_verifiable"), int(result.get("score", 0)), json.dumps(result, ensure_ascii=False), int(time.time())),
        )


def history(user_id: int, limit: int = 20):
    import json
    with _db() as db:
        rows = db.execute("SELECT id, content_type, content, result_json, created_at FROM analyses WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user_id, min(limit, 100))).fetchall()
    out = []
    for row in rows:
        try:
            result = json.loads(row["result_json"])
        except Exception:
            result = {}
        result["__id"] = row["id"]
        result["__created_at"] = row["created_at"]
        result["__content_type"] = row["content_type"]
        out.append(result)
    return out


init_db()
