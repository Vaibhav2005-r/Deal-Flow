"""Integration test for dynamic authentication and registration."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_existing_user_login_success(client: TestClient):
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


def test_invalid_credentials_rejected(client: TestClient):
    res = client.post("/api/auth/login", json={
        "email": "priya.raghavan@dealflow.example",
        "password": "wrong_password_xyz",
    })
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid credentials"


def test_registration_and_login_flow(client: TestClient):
    new_email = "marcus.vance@acmecorp.com"
    new_password = "SecurePassword#2026"

    # Register new user
    reg_res = client.post("/api/auth/register", json={
        "email": new_email,
        "password": new_password,
        "full_name": "Marcus Vance",
        "role": "manager",
    })
    assert reg_res.status_code == 201
    data = reg_res.json()
    # EXPECTATION CHANGED, deliberately. This previously asserted that a public
    # registration claiming "manager" was granted it. That was the behaviour of
    # a privilege-escalation hole: anyone could POST {"role": "admin"} to this
    # endpoint and receive every capability -- approve their own over-ceiling
    # quotes, rewrite the discount policy, record payments. Self-service accounts
    # are now always a rep; approver roles are granted by an existing admin.
    assert data["role"] == "rep"
    assert data["full_name"] == "Marcus Vance"
    assert "token" in data

    # Login with newly created user
    login_res = client.post("/api/auth/login", json={
        "email": new_email,
        "password": new_password,
    })
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert login_data["role"] == "rep"
    assert login_data["full_name"] == "Marcus Vance"
    assert login_data["scope"] == "internal"


def test_finance_signup_and_duplicate_error(client: TestClient):
    email = "test.finance@enterprise.com"
    password = "FinancePassword123"

    # 1. Create Account with Finance Role
    res = client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "full_name": "Test Finance User",
        "role": "finance",
    })
    assert res.status_code == 201
    body = res.json()
    # EXPECTATION CHANGED, deliberately. This previously asserted that a public
    # registration claiming "finance" was granted it. That was the behaviour of
    # a privilege-escalation hole: anyone could POST {"role": "admin"} to this
    # endpoint and receive every capability -- approve their own over-ceiling
    # quotes, rewrite the discount policy, record payments. Self-service accounts
    # are now always a rep; approver roles are granted by an existing admin.
    assert body["role"] == "rep"
    assert body["full_name"] == "Test Finance User"
    assert body["scope"] == "internal"
    assert "token" in body

    # 2. Duplicate registration returns 409 (not 500)
    dup = client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "full_name": "Duplicate Finance User",
        "role": "finance",
    })
    assert dup.status_code == 409
    assert "already exists" in dup.json()["detail"]

    # 3. Validation errors return 400 (not 500)
    bad_email = client.post("/api/auth/register", json={
        "email": "invalidemail",
        "password": password,
        "full_name": "Bad Email",
    })
    assert bad_email.status_code == 400

    bad_pass = client.post("/api/auth/register", json={
        "email": "another@test.com",
        "password": "1",
        "full_name": "Short Pass",
    })
    assert bad_pass.status_code == 400
