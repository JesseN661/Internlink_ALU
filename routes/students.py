"""
routes/students.py
------------------
Student-facing routes for InternLink.

Endpoints
---------
GET  /student/dashboard           – Personalised dashboard + recommendations
GET  /student/profile             – View own profile
POST /student/profile/update      – Update profile (skills, preferences, etc.)
POST /student/profile/upload      – Upload resume (PDF, max 5 MB)
GET  /student/applications        – List student's own applications
POST /student/apply/<intern_id>   – Apply for an internship
POST /student/feedback            – Submit feedback about an internship
GET  /student/internships         – Browse all active internships (with search)
"""

import os
from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, session, current_app,
)
from utils.db           import get_db_connection
from utils.auth_utils   import login_required, role_required, sanitize_string
from utils.matching     import get_recommendations_for_student
from mysql.connector    import Error
from werkzeug.utils     import secure_filename

students_bp = Blueprint("students", __name__, url_prefix="/student")

ALLOWED_EXTENSIONS = {"pdf"}


def _upload_folder() -> str:
    """Return absolute path to uploads dir, always relative to app root."""
    folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    return folder


def _allowed_file(filename: str) -> bool:
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_student(student_id: str, conn) -> dict | None:
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM students WHERE id = %s", (student_id,))
    row = cursor.fetchone()
    cursor.close()
    return row


# ── Dashboard ─────────────────────────────────────────────────────────────────

@students_bp.route("/dashboard")
@role_required("student")
def dashboard():
    """
    Show:
    - Student profile summary
    - AI-matched internship recommendations
    - Recent applications
    """
    student_id = session["user_id"]
    conn = get_db_connection()
    if conn is None:
        flash("Database unavailable.", "danger")
        return render_template("dashboard.html", student=None,
                               recommendations=[], applications=[])

    student = _get_student(student_id, conn)

    # ── Matched recommendations ───────────────────────────────────────────────
    recommendations = []
    if student:
        recommendations = get_recommendations_for_student(student, conn)

    # ── Recent applications (last 10) ─────────────────────────────────────────
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT a.id, a.status, a.application_date,
               i.title, i.location, s.company_name
        FROM   applications a
        JOIN   internships  i ON i.id = a.internship_id
        JOIN   smes         s ON s.id = i.sme_id
        WHERE  a.student_id = %s
        ORDER  BY a.application_date DESC
        LIMIT  10
        """,
        (student_id,),
    )
    applications = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template(
        "dashboard.html",
        student        = student,
        recommendations= recommendations,
        applications   = applications,
    )


# ── Profile view ──────────────────────────────────────────────────────────────

@students_bp.route("/profile")
@role_required("student")
def profile():
    conn    = get_db_connection()
    student = _get_student(session["user_id"], conn) if conn else None
    if conn:
        conn.close()
    return render_template("student_profile.html", student=student)


# ── Profile update ────────────────────────────────────────────────────────────

@students_bp.route("/profile/update", methods=["POST"])
@role_required("student")
def update_profile():
    student_id  = session["user_id"]
    first_name  = sanitize_string(request.form.get("first_name",  ""), 80)
    last_name   = sanitize_string(request.form.get("last_name",   ""), 80)
    university  = sanitize_string(request.form.get("university",  ""), 150)
    major       = sanitize_string(request.form.get("major",       ""), 100)
    grad_year   = request.form.get("graduation_year", "")
    skills      = sanitize_string(request.form.get("skills",      ""), 500)
    preferences = sanitize_string(request.form.get("preferences", ""), 500)

    grad_year_val = int(grad_year) if grad_year.isdigit() else None

    conn = get_db_connection()
    if conn is None:
        flash("Database unavailable.", "danger")
        return redirect(url_for("students.profile"))

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE students
               SET first_name = %s, last_name = %s, university = %s,
                   major = %s, graduation_year = %s,
                   skills = %s, preferences = %s
             WHERE id = %s
            """,
            (first_name, last_name, university, major,
             grad_year_val, skills, preferences, student_id),
        )
        conn.commit()
        # Update session name
        session["name"] = f"{first_name} {last_name}"
        flash("Profile updated successfully.", "success")
    except Error as e:
        conn.rollback()
        flash(f"Update failed: {e}", "danger")
    finally:
        cursor.close(); conn.close()

    return redirect(url_for("students.profile"))


# ── Resume upload ─────────────────────────────────────────────────────────────

@students_bp.route("/profile/upload", methods=["POST"])
@role_required("student")
def upload_resume():
    student_id = session["user_id"]

    if "resume" not in request.files:
        flash("No file selected.", "warning")
        return redirect(url_for("students.profile"))

    file = request.files["resume"]
    if file.filename == "":
        flash("No file selected.", "warning")
        return redirect(url_for("students.profile"))

    if not _allowed_file(file.filename):
        flash("Only PDF files are accepted.", "danger")
        return redirect(url_for("students.profile"))

    file.seek(0, 2)
    size = file.tell()
    file.seek(0)
    if size > current_app.config["MAX_CONTENT_LENGTH"]:
        flash("File exceeds the 5 MB limit.", "danger")
        return redirect(url_for("students.profile"))

    filename  = secure_filename(f"{student_id}_resume.pdf")
    save_path = os.path.join(_upload_folder(), filename)
    file.save(save_path)

    # Store a relative URL in the DB
    resume_url = f"/uploads/{filename}"
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE students SET resume_url = %s WHERE id = %s",
            (resume_url, student_id),
        )
        conn.commit()
        cursor.close(); conn.close()

    flash("Resume uploaded successfully.", "success")
    return redirect(url_for("students.profile"))


# ── Browse internships ────────────────────────────────────────────────────────

@students_bp.route("/internships")
@role_required("student")
def browse_internships():
    """
    List active internships with optional keyword search
    (matches title, description, location, or skills_required).
    """
    query    = request.args.get("q", "").strip()
    location = request.args.get("location", "").strip()
    skill    = request.args.get("skill", "").strip()

    conn = get_db_connection()
    if conn is None:
        flash("Database unavailable.", "danger")
        return render_template("internships_list.html", internships=[], query=query)

    cursor = conn.cursor(dictionary=True)

    sql    = """
        SELECT i.*, s.company_name, s.industry
        FROM   internships i
        JOIN   smes s ON s.id = i.sme_id
        WHERE  i.is_active = TRUE
    """
    params = []

    if query:
        sql   += " AND (i.title LIKE %s OR i.description LIKE %s OR i.skills_required LIKE %s)"
        like   = f"%{query}%"
        params += [like, like, like]
    if location:
        sql   += " AND i.location LIKE %s"
        params.append(f"%{location}%")
    if skill:
        sql   += " AND i.skills_required LIKE %s"
        params.append(f"%{skill}%")

    sql += " ORDER BY i.created_at DESC LIMIT 50"

    cursor.execute(sql, params)
    internships = cursor.fetchall()
    cursor.close(); conn.close()

    return render_template(
        "internships_list.html",
        internships = internships,
        query       = query,
        location    = location,
        skill       = skill,
    )


# ── Apply for internship ──────────────────────────────────────────────────────

@students_bp.route("/apply/<internship_id>", methods=["POST"])
@role_required("student")
def apply(internship_id: str):
    student_id = session["user_id"]

    conn = get_db_connection()
    if conn is None:
        flash("Database unavailable.", "danger")
        return redirect(url_for("students.browse_internships"))

    cursor = conn.cursor(dictionary=True)

    # Check internship exists and is active
    cursor.execute(
        "SELECT id, title, is_active FROM internships WHERE id = %s",
        (internship_id,),
    )
    internship = cursor.fetchone()

    if not internship or not internship["is_active"]:
        flash("Internship not found or no longer active.", "warning")
        cursor.close(); conn.close()
        return redirect(url_for("students.browse_internships"))

    # Check for duplicate application
    cursor.execute(
        "SELECT id FROM applications WHERE student_id = %s AND internship_id = %s",
        (student_id, internship_id),
    )
    if cursor.fetchone():
        flash("You have already applied for this internship.", "info")
        cursor.close(); conn.close()
        return redirect(url_for("students.applications"))

    # Insert application
    cover_letter = sanitize_string(request.form.get("cover_letter", ""), 2000)
    try:
        cursor.execute(
            """
            INSERT INTO applications (student_id, internship_id, cover_letter, status)
            VALUES (%s, %s, %s, 'pending')
            """,
            (student_id, internship_id, cover_letter or None),
        )
        conn.commit()
        flash(f"Successfully applied for '{internship['title']}'!", "success")
    except Error as e:
        conn.rollback()
        flash(f"Application failed: {e}", "danger")
    finally:
        cursor.close(); conn.close()

    return redirect(url_for("students.applications"))


# ── View own applications ─────────────────────────────────────────────────────

@students_bp.route("/applications")
@role_required("student")
def applications():
    student_id = session["user_id"]
    conn = get_db_connection()
    if conn is None:
        flash("Database unavailable.", "danger")
        return render_template("applications.html", applications=[])

    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT a.id, a.status, a.application_date, a.decision_date,
               a.internship_id,
               i.title, i.location, i.start_date, i.end_date,
               i.sme_id,
               s.company_name, s.industry
        FROM   applications a
        JOIN   internships  i ON i.id = a.internship_id
        JOIN   smes         s ON s.id = i.sme_id
        WHERE  a.student_id = %s
        ORDER  BY a.application_date DESC
        """,
        (student_id,),
    )
    apps = cursor.fetchall()
    cursor.close(); conn.close()

    return render_template("applications.html", applications=apps)


# ── Submit feedback ───────────────────────────────────────────────────────────

@students_bp.route("/feedback", methods=["POST"])
@role_required("student")
def submit_feedback():
    student_id    = session["user_id"]
    internship_id = request.form.get("internship_id", "")
    sme_id        = request.form.get("sme_id", "")
    rating        = request.form.get("rating", "")
    comments      = sanitize_string(request.form.get("comments", ""), 1000)

    if not internship_id or not sme_id or not rating.isdigit():
        flash("Invalid feedback submission.", "danger")
        return redirect(url_for("students.applications"))

    rating_int = int(rating)
    if not (1 <= rating_int <= 5):
        flash("Rating must be between 1 and 5.", "danger")
        return redirect(url_for("students.applications"))

    conn = get_db_connection()
    if conn is None:
        flash("Database unavailable.", "danger")
        return redirect(url_for("students.applications"))

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO feedback
                (student_id, sme_id, internship_id, submitted_by, rating, comments)
            VALUES (%s, %s, %s, 'student', %s, %s)
            """,
            (student_id, sme_id, internship_id, rating_int, comments),
        )
        conn.commit()
        flash("Thank you for your feedback!", "success")
    except Error as e:
        conn.rollback()
        flash(f"Feedback submission failed: {e}", "danger")
    finally:
        cursor.close(); conn.close()

    return redirect(url_for("students.applications"))
