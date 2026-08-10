"""
Integration tests against the FastAPI app. These require a real Postgres
instance (see docker-compose.yml's `db` service, or point DATABASE_URL at a
disposable test database) — they are not run against SQLite because the
schema uses native Postgres UUID columns.

Run with: `docker compose exec backend pytest tests/test_auth_api.py`
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.seed.seed_data import DEMO_ADMIN_EMAIL, DEMO_ADMIN_PASSWORD, seed

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def ensure_seeded():
    seed()


def test_health_check():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_login_success():
    response = client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_ADMIN_EMAIL, "password": DEMO_ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body


def test_login_wrong_password():
    response = client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_ADMIN_EMAIL, "password": "wrong-password"},
    )
    assert response.status_code == 401


def test_me_requires_auth():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 403  # HTTPBearer with auto_error raises 403 when header missing


def test_me_with_valid_token():
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_ADMIN_EMAIL, "password": DEMO_ADMIN_PASSWORD},
    )
    token = login_response.json()["access_token"]

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == DEMO_ADMIN_EMAIL
    assert response.json()["role"]["name"] == "admin"


def test_users_list_requires_admin_role():
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_ADMIN_EMAIL, "password": DEMO_ADMIN_PASSWORD},
    )
    token = login_response.json()["access_token"]
    response = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
