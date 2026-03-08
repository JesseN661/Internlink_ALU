"""
routes/auth.py
--------------
Authentication blueprint for InternLink.

Endpoints
---------
GET  /register          – Show registration page (role selection)
POST /register/student  – Create student account
POST /register/sme      – Create SME account
GET  /login             – Show login form
POST /login             – Authenticate and start session
GET  /logout            – Destroy session
"""

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, session,
)
from utils.db        import get_db_connection
from utils.auth_utils import (
    hash_password, verify_password,
    validate_email, validate_password, sanitize_string,
    login_user, logout_user,
)
from mysql.connector import Error

auth_bp = Blueprint("auth", __name__)


# ── Register page ─────────────────────────────────────────────────────────────

@auth_bp.route("/register")
def register():
    """Render role-selection / registration landing page."""
    return render_template("register.html")


# ── Student registration ──────────────────────────────────────────────────────

@auth_bp.route("/register/student", methods=["POST"])
def register_student():
    first_name  = sanitize_string(request.form.get("first_name", ""), 80)
    last_name   = sanitize_string(request.form.get("last_name",  ""), 80)
    email       = sanitize_string(request.form.get("email",      ""), 120)
    password    = request.form.get("password", "")
    university  = sanitize_string(request.form.get("university", ""), 150)
    major       = sanitize_string(request.form.get("major",      ""), 100)
    grad_year   = request.form.get("graduation_year", "")
    skills      = sanitize_string(request.form.get("skills",     ""), 500)
    preferences = sanitize_string(request.form.get("preferences",""), 500)

    # ── Validate ──────────────────────────────────────────────────────────────
    errors = []
    if not first_name or not last_name:
        errors.append("First and last name are required.")
    if not validate_email(email):
        errors.append("Invalid email address.")
    if not validate_password(password):
        errors.append("Password must be 8–128 characters.")

    if errors:
        for e in errors:
            flash(e, "danger")
        return redirect(url_for("auth.register"))

    # ── Check duplicate email ─────────────────────────────────────────────────
    conn = get_db_connection()
    if conn is None:
        flash("Database unavailable. Please try later.", "danger")
        return redirect(url_for("auth.register"))

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM students WHERE email = %s", (email,))
    if cursor.fetchone():
        flash("An account with that email already exists.", "warning")
        cursor.close(); conn.close()
        return redirect(url_for("auth.register"))

    # ── Insert ────────────────────────────────────────────────────────────────
    hashed = hash_password(password)
    grad_year_val = int(grad_year) if grad_year.isdigit() else None

    try:
        cursor.execute(
            """
            INSERT INTO students
                (first_name, last_name, email, password,
                 university, major, graduation_year, skills, preferences)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (first_name, last_name, email, hashed,
             university, major, grad_year_val, skills, preferences),
        )
        conn.commit()

        # Fetch new row to get generated UUID
        cursor.execute("SELECT id FROM students WHERE email = %s", (email,))
        row = cursor.fetchone()
        login_user(row["id"], "student", f"{first_name} {last_name}")

    except Error as e:
        conn.rollback()
        flash(f"Registration failed: {e}", "danger")
        return redirect(url_for("auth.register"))
    finally:
        cursor.close(); conn.close()

    flash("Welcome to InternLink! Your account has been created.", "success")
    return redirect(url_for("students.dashboard"))


# ── SME registration ──────────────────────────────────────────────────────────

@auth_bp.route("/register/sme", methods=["POST"])
def register_sme():
    company_name  = sanitize_string(request.form.get("company_name",  ""), 150)
    contact_name  = sanitize_string(request.form.get("contact_name",  ""), 120)
    email         = sanitize_string(request.form.get("email",         ""), 120)
    password      = request.form.get("password", "")
    industry      = sanitize_string(request.form.get("industry",      ""), 100)
    website       = sanitize_string(request.form.get("company_website",""), 255)

    # ── Validate ──────────────────────────────────────────────────────────────
    errors = []
    if not company_name or not contact_name:
        errors.append("Company name and contact name are required.")
    if not validate_email(email):
        errors.append("Invalid email address.")
    if not validate_password(password):
        errors.append("Password must be 8–128 characters.")

    if errors:
        for e in errors:
            flash(e, "danger")
        return redirect(url_for("auth.register"))

    conn = get_db_connection()
    if conn is None:
        flash("Database unavailable. Please try later.", "danger")
        return redirect(url_for("auth.register"))

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM smes WHERE contact_email = %s", (email,))
    if cursor.fetchone():
        flash("An account with that email already exists.", "warning")
        cursor.close(); conn.close()
        return redirect(url_for("auth.register"))

    hashed = hash_password(password)
    try:
        cursor.execute(
            """
            INSERT INTO smes
                (company_name, contact_name, contact_email,
                 password, industry, company_website)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (company_name, contact_name, email, hashed, industry, website),
        )
        conn.commit()

        cursor.execute("SELECT id FROM smes WHERE contact_email = %s", (email,))
        row = cursor.fetchone()
        login_user(row["id"], "sme", company_name)

    except Error as e:
        conn.rollback()
        flash(f"Registration failed: {e}", "danger")
        return redirect(url_for("auth.register"))
    finally:
        cursor.close(); conn.close()

    flash("Welcome! Your company profile has been created.", "success")
    return redirect(url_for("internships.sme_dashboard"))


# ── Login ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email    = sanitize_string(request.form.get("email",    ""), 120)
    password = request.form.get("password", "")
    role     = request.form.get("role", "student")   # student | sme | admin

    if not validate_email(email) or not password:
        flash("Please enter a valid email and password.", "danger")
        return render_template("login.html")

    conn = get_db_connection()
    if conn is None:
        flash("Database unavailable. Please try later.", "danger")
        return render_template("login.html")

    cursor = conn.cursor(dictionary=True)

    user     = None
    name     = ""
    redirect_to = "students.dashboard"

    try:
        if role == "student":
            cursor.execute(
                "SELECT id, first_name, last_name, password FROM students WHERE email = %s",
                (email,),
            )
            row = cursor.fetchone()
            if row and verify_password(password, row["password"]):
                user = row
                name = f"{row['first_name']} {row['last_name']}"
                redirect_to = "students.dashboard"

        elif role == "sme":
            cursor.execute(
                "SELECT id, company_name, password FROM smes WHERE contact_email = %s",
                (email,),
            )
            row = cursor.fetchone()
            if row and verify_password(password, row["password"]):
                user = row
                name = row["company_name"]
                redirect_to = "internships.sme_dashboard"

        elif role == "admin":
            cursor.execute(
                "SELECT id, username, password FROM admins WHERE email = %s",
                (email,),
            )
            row = cursor.fetchone()
            if row and verify_password(password, row["password"]):
                user = row
                name = row["username"]
                redirect_to = "auth.admin_panel"

    finally:
        cursor.close(); conn.close()

    if user is None:
        flash("Invalid email, password, or role.", "danger")
        return render_template("login.html")

    login_user(user["id"], role, name)
    flash(f"Welcome back, {name}!", "success")
    return redirect(url_for(redirect_to))


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout")
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


# ── Minimal admin panel (placeholder) ────────────────────────────────────────

@auth_bp.route("/admin")
def admin_panel():
    if session.get("role") != "admin":
        flash("Access denied.", "danger")
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    if conn is None:
        return render_template("admin.html", stats={})

    cursor = conn.cursor(dictionary=True)
    stats  = {}
    _ALLOWED_TABLES = ("students", "smes", "internships", "applications", "feedback")
    for table in _ALLOWED_TABLES:
        cursor.execute(f"SELECT COUNT(*) AS cnt FROM `{table}`")  # table name from allowlist only
        stats[table] = cursor.fetchone()["cnt"]
    cursor.close(); conn.close()

    return render_template("admin.html", stats=stats)

