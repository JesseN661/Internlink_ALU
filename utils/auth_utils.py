"""
utils/auth_utils.py
-------------------
Password hashing (PBKDF2-SHA256) and session management helpers
for InternLink.  No third-party crypto libraries required beyond
the Python standard library.
"""

import hashlib
import hmac
import os
import re
import binascii
from functools import wraps
from flask import session, redirect, url_for, flash


# ── Constants ─────────────────────────────────────────────────────────────────

HASH_ALGO      = "sha256"
HASH_ITER      = 260_000          # NIST-recommended minimum (2023)
SALT_BYTES     = 32
SEPARATOR      = "$"              # format: algo$iter$salt_hex$key_hex


# ── Hashing ───────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """
    Hash *plain* with PBKDF2-HMAC-SHA256.

    Returns a self-describing string:
        sha256$260000$<salt_hex>$<key_hex>

    >>> stored = hash_password("secret")
    >>> verify_password("secret", stored)
    True
    """
    salt = os.urandom(SALT_BYTES)
    key  = hashlib.pbkdf2_hmac(
        HASH_ALGO,
        plain.encode("utf-8"),
        salt,
        HASH_ITER,
    )
    return SEPARATOR.join([
        HASH_ALGO,
        str(HASH_ITER),
        binascii.hexlify(salt).decode("ascii"),
        binascii.hexlify(key).decode("ascii"),
    ])


def verify_password(plain: str, stored: str) -> bool:
    """
    Constant-time comparison to guard against timing attacks.

    Args:
        plain:  Password provided at login.
        stored: Value returned by hash_password() and saved in DB.

    Returns:
        True if the password matches, False otherwise.
    """
    try:
        algo, iterations, salt_hex, key_hex = stored.split(SEPARATOR)
    except ValueError:
        return False

    salt        = binascii.unhexlify(salt_hex)
    expected    = binascii.unhexlify(key_hex)
    iterations  = int(iterations)

    candidate = hashlib.pbkdf2_hmac(
        algo,
        plain.encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(candidate, expected)


# ── Input validation ──────────────────────────────────────────────────────────

_EMAIL_RE    = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PASSWORD_RE = re.compile(r"^.{8,128}$")           # 8-128 chars


def validate_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email.strip()))


def validate_password(password: str) -> bool:
    """Minimum 8 characters, maximum 128."""
    return bool(_PASSWORD_RE.match(password))


def sanitize_string(value: str, max_length: int = 255) -> str:
    """Strip whitespace and truncate to *max_length*."""
    return value.strip()[:max_length]


# ── Session helpers ───────────────────────────────────────────────────────────

def login_user(user_id: str, role: str, name: str) -> None:
    """
    Write user info into the Flask session.

    Args:
        user_id: UUID from the relevant DB table.
        role:    One of 'student', 'sme', 'admin'.
        name:    Display name shown in the UI.
    """
    session.clear()
    session["user_id"] = user_id
    session["role"]    = role
    session["name"]    = name


def logout_user() -> None:
    """Wipe the session on logout."""
    session.clear()


def current_user_id() -> str | None:
    return session.get("user_id")


def current_role() -> str | None:
    return session.get("role")


def is_logged_in() -> bool:
    return "user_id" in session


# ── Decorators ────────────────────────────────────────────────────────────────

def login_required(f):
    """
    Redirect to /login if the user is not authenticated.

    Usage::

        @app.route("/dashboard")
        @login_required
        def dashboard():
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_logged_in():
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    """
    Restrict a route to specific roles.

    Usage::

        @app.route("/admin")
        @role_required("admin")
        def admin_panel():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not is_logged_in():
                flash("Please log in to continue.", "warning")
                return redirect(url_for("auth.login"))
            if current_role() not in roles:
                flash("Access denied.", "danger")
                return redirect(url_for("auth.login"))
            return f(*args, **kwargs)
        return decorated
    return decorator
