import os
from pathlib import Path

os.environ["TRUTHCHECKER_DB_PATH"] = str(Path(__file__).parent / "test_truthchecker.db")
os.environ["AUTH_SECRET"] = "test-secret-for-auth"

from fastapi.testclient import TestClient
from main import app
from app import auth


def setup_function():
    auth.init_db()
    with auth._db() as db:
        db.execute("DELETE FROM analyses")
        db.execute("DELETE FROM users")


def teardown_module():
    p = Path(__file__).parent / "test_truthchecker.db"
    if p.exists(): p.unlink()


def test_register_login_me():
    client = TestClient(app)
    r = client.post("/api/auth/register", json={"email":"test@example.com", "password":"password1"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert token
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "test@example.com"
    login = client.post("/api/auth/login", json={"email":"test@example.com", "password":"password1"})
    assert login.status_code == 200


def test_analyze_requires_auth():
    client = TestClient(app)
    r = client.post("/api/analyze", json={"type":"text","content":"hello","language":"fr"})
    assert r.status_code == 401
