"""No password may authenticate an account it does not belong to.

A merge added a "convenience fallback for seeded demo accounts" to
verify_password that returned True whenever the submitted password was
"password", "demo" or "dealflow". It never consulted `password_hash`, so it was
not scoped to a demo account, or to any account: it authenticated every seeded
user in the database, root@dealflow.example among them -- admin, all nineteen
capabilities -- on two public repositories.

It read as a harmless demo shortcut, which is exactly why it needs a test
rather than a code comment. The safe version of that convenience already
exists: /api/auth/demo-accounts serves the real seeded credentials to the
sign-in screen's role buttons.
"""

from __future__ import annotations

import pytest

from app.api.security import hash_password, verify_password

#: The literals the removed fallback accepted, plus the usual suspects a
#: future "just for the demo" patch would reach for.
COMMON_GUESSES = [
    "password", "demo", "dealflow", "Password", "  password  ",
    "DEMO", "admin", "letmein", "test", "123456",
]


@pytest.fixture
def seeded_hash() -> str:
    """A seeded-scheme hash, as app/seed.py writes them."""
    import hashlib

    return "seed$" + hashlib.sha256(b"demo::root@dealflow.example").hexdigest()


@pytest.mark.parametrize("guess", COMMON_GUESSES)
def test_a_guess_never_authenticates_a_seeded_account(seeded_hash, guess):
    assert verify_password(guess, seeded_hash) is False, (
        f"{guess!r} authenticated a seeded account it does not belong to"
    )


@pytest.mark.parametrize("guess", COMMON_GUESSES)
def test_a_guess_never_authenticates_a_real_account(guess):
    stored = hash_password("the-actual-password")
    assert verify_password(guess, stored) is False


def test_the_correct_seeded_password_still_works(seeded_hash):
    """The guard must not have been implemented by breaking sign-in."""
    assert verify_password("root@dealflow.example", seeded_hash) is True


def test_the_correct_real_password_still_works():
    stored = hash_password("the-actual-password")
    assert verify_password("the-actual-password", stored) is True
    assert verify_password("the-actual-passwore", stored) is False


def test_seeded_accounts_do_not_share_a_password():
    """Each seeded hash accepts only its own string.

    The fallback made every seeded account interchangeable; this fails if
    anything like it returns.
    """
    import hashlib

    def seeded(secret: str) -> str:
        return "seed$" + hashlib.sha256(f"demo::{secret}".encode()).hexdigest()

    a, b = "priya.raghavan@dealflow.example", "root@dealflow.example"
    assert verify_password(a, seeded(a)) is True
    assert verify_password(a, seeded(b)) is False
    assert verify_password(b, seeded(a)) is False


def test_verify_password_reads_the_hash_it_is_given():
    """An empty or junk hash must never authenticate anything.

    A fallback that ignores `password_hash` shows up here immediately.
    """
    for junk in ("", "not-a-hash", "seed$", "pbkdf2$", "seed$deadbeef"):
        for guess in ("password", "demo", "dealflow", "anything"):
            assert verify_password(guess, junk) is False
