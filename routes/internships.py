"""
routes/internships.py
---------------------
SME-facing routes for InternLink.

Endpoints
---------
GET  /sme/dashboard                    – SME dashboard (stats + listings)
GET  /sme/internship/new               – Show "post internship" form
POST /sme/internship/new               – Create new internship posting
GET  /sme/internship/<id>/edit         – Edit internship form
POST /sme/internship/<id>/edit         – Save internship edits
POST /sme/internship/<id>/toggle       – Toggle is_active (open / close)
POST /sme/internship/<id>/delete       – Delete internship
GET  /sme/internship/<id>/candidates   – View applicants for an internship
POST /sme/application/<id>/decide      – Accept or reject an application
"""

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash, session,
)
from utils.db         import get_db_connection
from utils.auth_utils import role_required, sanitize_string
from mysql.connector  import Error

internships_bp = Blueprint("internships", __name__, url_prefix="/sme")


# ── SME dashboard ─────────────────────────────────────────────────────────────

@internships_bp.route("/dashboard")
@role_required("sme")
def sme_dashboard():
    """
    Show:
    - Company profile summary
    - All internship listings with application counts
    - Recent applications across all postings
    """
    sme_id = session["user_id"]
    conn   = get_db_connection()
    if conn is None:
        flash("Database unavailable.", "danger")
        return render_template("sme_dashboard.html", sme=None,
                               internships=[], recent_apps=[])

    cursor = conn.cursor(dictionary=True)

    # SME profile
    cursor.execute("SELECT * FROM smes WHERE id = %s", (sme_id,))
    sme = cursor.fetchone()

    # Internships with application count
    cursor.execute(
        """
        SELECT i.*,
               COUNT(a.id)                                           AS total_apps,
               SUM(a.status = 'accepted')                           AS accepted,
               SUM(a.status = 'pending')                            AS pending_count
        FROM   internships i
        LEFT   JOIN applications a ON a.internship_id = i.id
        WHERE  i.sme_id = %s
        GROUP  BY i.id
        ORDER  BY i.created_at DESC
        """,
        (sme_id,),
    )
    internship_list = cursor.fetchall()

    # Recent 10 applications across all postings
    cursor.execute(
        """
        SELECT a.id, a.status, a.application_date,
               st.first_name, st.last_name, st.email, st.skills,
               i.title AS internship_title
        FROM   applications a
        JOIN   students    st ON st.id = a.student_id
        JOIN   internships  i ON  i.id = a.internship_id
        WHERE  i.sme_id = %s
        ORDER  BY a.application_date DESC
        LIMIT  10
        """,
        (sme_id,),
    )
    recent_apps = cursor.fetchall()

    cursor.close(); conn.close()

    return render_template(
        "sme_dashboard.html",
        sme         = sme,
        internships = internship_list,
        recent_apps = recent_apps,
    )


# ── Post new internship ───────────────────────────────────────────────────────

@internships_bp.route("/internship/new", methods=["GET", "POST"])
@role_required("sme")
def new_internship():
    if request.method == "GET":
        return render_template("internship_form.html", internship=None)

    sme_id          = session["user_id"]
    title           = sanitize_string(request.form.get("title",          ""), 150)
    description     = sanitize_string(request.form.get("description",    ""), 2000)
    location        = sanitize_string(request.form.get("location",       ""), 100)
    skills_required = sanitize_string(request.form.get("skills_required",""), 500)
    start_date      = request.form.get("start_date", "") or None
    end_date        = request.form.get("end_date",   "") or None

    if not title:
        flash("Internship title is required.", "danger")
        return render_template("internship_form.html", internship=None)

    conn = get_db_connection()
    if conn is None:
        flash("Database unavailable.", "danger")
        return render_template("internship_form.html", internship=None)

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO internships
                (sme_id, title, description, location,
                 skills_required, start_date, end_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (sme_id, title, description, location,
             skills_required, start_date, end_date),
        )
        conn.commit()
        flash(f'"{title}" has been posted successfully.', "success")
    except Error as e:
        conn.rollback()
        flash(f"Failed to post internship: {e}", "danger")
    finally:
        cursor.close(); conn.close()

    return redirect(url_for("internships.sme_dashboard"))


# ── Edit internship ───────────────────────────────────────────────────────────

@internships_bp.route("/internship/<internship_id>/edit", methods=["GET", "POST"])
@role_required("sme")
def edit_internship(internship_id: str):
    sme_id = session["user_id"]
    conn   = get_db_connection()
    if conn is None:
        flash("Database unavailable.", "danger")
        return redirect(url_for("internships.sme_dashboard"))

    cursor = conn.cursor(dictionary=True)

    if request.method == "GET":
        cursor.execute(
            "SELECT * FROM internships WHERE id = %s AND sme_id = %s",
            (internship_id, sme_id),
        )
        internship = cursor.fetchone()
        cursor.close(); conn.close()

        if not internship:
            flash("Internship not found.", "warning")
            return redirect(url_for("internships.sme_dashboard"))

        return render_template("internship_form.html", internship=internship)

    # POST – save edits
    title           = sanitize_string(request.form.get("title",          ""), 150)
    description     = sanitize_string(request.form.get("description",    ""), 2000)
    location        = sanitize_string(request.form.get("location",       ""), 100)
    skills_required = sanitize_string(request.form.get("skills_required",""), 500)
    start_date      = request.form.get("start_date", "") or None
    end_date        = request.form.get("end_date",   "") or None

    try:
        cursor.execute(
            """
            UPDATE internships
               SET title = %s, description = %s, location = %s,
                   skills_required = %s, start_date = %s, end_date = %s
             WHERE id = %s AND sme_id = %s
            """,
            (title, description, location, skills_required,
             start_date, end_date, internship_id, sme_id),
        )
        conn.commit()
        flash("Internship updated.", "success")
    except Error as e:
        conn.rollback()
        flash(f"Update failed: {e}", "danger")
    finally:
        cursor.close(); conn.close()

    return redirect(url_for("internships.sme_dashboard"))


# ── Toggle active/inactive ────────────────────────────────────────────────────

@internships_bp.route("/internship/<internship_id>/toggle", methods=["POST"])
@role_required("sme")
def toggle_internship(internship_id: str):
    sme_id = session["user_id"]
    conn   = get_db_connection()
    if conn is None:
        flash("Database unavailable.", "danger")
        return redirect(url_for("internships.sme_dashboard"))

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE internships
               SET is_active = NOT is_active
             WHERE id = %s AND sme_id = %s
            """,
            (internship_id, sme_id),
        )
        conn.commit()
        flash("Internship status updated.", "success")
    except Error as e:
        conn.rollback()
        flash(f"Failed to update status: {e}", "danger")
    finally:
        cursor.close(); conn.close()

    return redirect(url_for("internships.sme_dashboard"))


# ── Delete internship ─────────────────────────────────────────────────────────

@internships_bp.route("/internship/<internship_id>/delete", methods=["POST"])
@role_required("sme")
def delete_internship(internship_id: str):
    sme_id = session["user_id"]
    conn   = get_db_connection()
    if conn is None:
        flash("Database unavailable.", "danger")
        return redirect(url_for("internships.sme_dashboard"))

    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM internships WHERE id = %s AND sme_id = %s",
            (internship_id, sme_id),
        )
        conn.commit()
        flash("Internship deleted.", "info")
    except Error as e:
        conn.rollback()
        flash(f"Delete failed: {e}", "danger")
    finally:
        cursor.close(); conn.close()

    return redirect(url_for("internships.sme_dashboard"))


# ── Candidate review ──────────────────────────────────────────────────────────

@internships_bp.route("/internship/<internship_id>/candidates")
@role_required("sme")
def candidates(internship_id: str):
    """
    List all applicants for a specific internship, showing their
    profile data and computed skill match score.
    """
    sme_id = session["user_id"]
    conn   = get_db_connection()
    if conn is None:
        flash("Database unavailable.", "danger")
        return redirect(url_for("internships.sme_dashboard"))

    cursor = conn.cursor(dictionary=True)

    # Verify ownership
    cursor.execute(
        "SELECT * FROM internships WHERE id = %s AND sme_id = %s",
        (internship_id, sme_id),
    )
    internship = cursor.fetchone()
    if not internship:
        flash("Internship not found.", "warning")
        cursor.close(); conn.close()
        return redirect(url_for("internships.sme_dashboard"))

    # Fetch all applicants
    cursor.execute(
        """
        SELECT a.id AS app_id, a.status, a.application_date, a.decision_date,
               st.id AS student_id, st.first_name, st.last_name,
               st.email, st.university, st.major, st.skills, st.resume_url
        FROM   applications a
        JOIN   students     st ON st.id = a.student_id
        WHERE  a.internship_id = %s
        ORDER  BY a.application_date ASC
        """,
        (internship_id,),
    )
    applicants = cursor.fetchall()
    cursor.close(); conn.close()

    # Attach live match scores
    from utils.matching import compute_match_score
    for app in applicants:
        app["match_score"] = compute_match_score(
            app.get("skills"),
            internship.get("skills_required"),
        )
    # Sort by match score descending
    applicants.sort(key=lambda a: a["match_score"], reverse=True)

    return render_template(
        "candidates.html",
        internship = internship,
        applicants = applicants,
    )


# ── Accept / Reject application ───────────────────────────────────────────────

@internships_bp.route("/application/<app_id>/decide", methods=["POST"])
@role_required("sme")
def decide_application(app_id: str):
    decision = request.form.get("decision", "")        # 'accepted' | 'rejected'
    sme_id   = session["user_id"]

    if decision not in ("accepted", "rejected"):
        flash("Invalid decision.", "danger")
        return redirect(url_for("internships.sme_dashboard"))

    conn = get_db_connection()
    if conn is None:
        flash("Database unavailable.", "danger")
        return redirect(url_for("internships.sme_dashboard"))

    cursor = conn.cursor(dictionary=True)

    # Verify the application belongs to one of this SME's internships
    cursor.execute(
        """
        SELECT a.id, a.internship_id
        FROM   applications a
        JOIN   internships  i ON i.id = a.internship_id
        WHERE  a.id = %s AND i.sme_id = %s
        """,
        (app_id, sme_id),
    )
    app = cursor.fetchone()

    if not app:
        flash("Application not found.", "warning")
        cursor.close(); conn.close()
        return redirect(url_for("internships.sme_dashboard"))

    try:
        cursor.execute(
            """
            UPDATE applications
               SET status = %s, reviewed_by_sme = TRUE,
                   decision_date = NOW()
             WHERE id = %s
            """,
            (decision, app_id),
        )
        conn.commit()
        flash(f"Application {decision}.", "success")
    except Error as e:
        conn.rollback()
        flash(f"Decision failed: {e}", "danger")
    finally:
        cursor.close(); conn.close()

    return redirect(url_for(
        "internships.candidates",
        internship_id=app["internship_id"],
    ))
