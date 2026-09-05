"""Integration test for dynamic authentication and registration."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_existing_user_login_success():
    client = TestClient(app)
    res = client.post("/api/auth/login", json={
        "email": "priya.raghavan@dealflow.example",
        "password": "priya.raghavan@dealflow.example",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["role"] == "rep"
    assert data["full_name"] == "Priya Raghavan"
    assert data["scope"] == "internal"
    assert "token" in data


def test_invalid_credentials_rejected():
    client = TestClient(app)
    res = client.post("/api/auth/login", json={
        "email": "priya.raghavan@dealflow.example",
        "password": "wrong_password_xyz",
    })
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid credentials"


def test_registration_and_login_flow():
    client = TestClient(app)
    new_email = "marcus.vance@acmecorp.com"
    new_password = "SecurePassword#2026"

    # Register new user
    reg_res = client.post("/api/auth/register", json={
        "email": new_email,
        "password": new_password,
        "full_name": "Marcus Vance",
        "role": "manager",
    })
    assert reg_res.status_code in (201, 409)

    # Login with newly created user
    login_res = client.post("/api/auth/login", json={
        "email": new_email,
        "password": new_password,
    })
    assert login_res.status_code == 200
    data = login_res.json()
    assert data["role"] == "manager"
    assert data["full_name"] == "Marcus Vance"
    assert data["scope"] == "internal"
