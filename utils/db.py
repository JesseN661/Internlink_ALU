"""
utils/db.py
-----------
Database connection and schema bootstrap for InternLink.
"""

import mysql.connector
from mysql.connector import Error
from config import active_config


def get_db_connection():
    """
    Create and return a MySQL connection using values from config.py.

    Returns:
        mysql.connector.MySQLConnection on success, None on failure.
    """
    try:
        conn = mysql.connector.connect(
            host=active_config.DB_HOST,
            user=active_config.DB_USER,
            password=active_config.DB_PASSWORD,
            database=active_config.DB_NAME,
            autocommit=False,
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
        )
        return conn
    except Error as e:
        print(f"[DB] Connection error: {e}")
        return None


# ── Schema ────────────────────────────────────────────────────────────────────

CREATE_TABLES_SQL = [
    """
    CREATE TABLE IF NOT EXISTS admins (
        id          VARCHAR(36)  PRIMARY KEY DEFAULT (UUID()),
        username    VARCHAR(80)  NOT NULL UNIQUE,
        email       VARCHAR(120) NOT NULL UNIQUE,
        password    VARCHAR(255) NOT NULL,
        role        VARCHAR(30)  NOT NULL DEFAULT 'moderator',
        created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """,

    """
    CREATE TABLE IF NOT EXISTS students (
        id                  VARCHAR(36)  PRIMARY KEY DEFAULT (UUID()),
        first_name          VARCHAR(80)  NOT NULL,
        last_name           VARCHAR(80)  NOT NULL,
        email               VARCHAR(120) NOT NULL UNIQUE,
        password            VARCHAR(255) NOT NULL,
        university          VARCHAR(150),
        major               VARCHAR(100),
        graduation_year     INT,
        skills              TEXT,
        preferences         TEXT,
        resume_url          VARCHAR(255),
        created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """,

    """
    CREATE TABLE IF NOT EXISTS smes (
        id                  VARCHAR(36)  PRIMARY KEY DEFAULT (UUID()),
        company_name        VARCHAR(150) NOT NULL,
        contact_name        VARCHAR(120) NOT NULL,
        contact_email       VARCHAR(120) NOT NULL UNIQUE,
        password            VARCHAR(255) NOT NULL,
        industry            VARCHAR(100),
        company_website     VARCHAR(255),
        created_at          TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB;
    """,

    """
    CREATE TABLE IF NOT EXISTS internships (
        id              VARCHAR(36)  PRIMARY KEY DEFAULT (UUID()),
        sme_id          VARCHAR(36)  NOT NULL,
        title           VARCHAR(150) NOT NULL,
        description     TEXT,
        location        VARCHAR(100),
        skills_required TEXT,
        start_date      DATE,
        end_date        DATE,
        is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
        created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sme_id) REFERENCES smes(id) ON DELETE CASCADE,
        INDEX idx_internships_sme_id  (sme_id),
        INDEX idx_internships_active  (is_active),
        INDEX idx_internships_created (created_at)
    ) ENGINE=InnoDB;
    """,

    """
    CREATE TABLE IF NOT EXISTS applications (
        id                VARCHAR(36)  PRIMARY KEY DEFAULT (UUID()),
        student_id        VARCHAR(36)  NOT NULL,
        internship_id     VARCHAR(36)  NOT NULL,
        cover_letter      TEXT,
        status            VARCHAR(20)  NOT NULL DEFAULT 'pending',
        reviewed_by_sme   BOOLEAN      NOT NULL DEFAULT FALSE,
        application_date  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        decision_date     TIMESTAMP    NULL,
        UNIQUE KEY uq_application (student_id, internship_id),
        FOREIGN KEY (student_id)    REFERENCES students(id)    ON DELETE CASCADE,
        FOREIGN KEY (internship_id) REFERENCES internships(id) ON DELETE CASCADE,
        INDEX idx_applications_student      (student_id),
        INDEX idx_applications_internship   (internship_id),
        INDEX idx_applications_status       (status)
    ) ENGINE=InnoDB;
    """,

    """
    CREATE TABLE IF NOT EXISTS feedback (
        id            VARCHAR(36)  PRIMARY KEY DEFAULT (UUID()),
        student_id    VARCHAR(36)  NOT NULL,
        sme_id        VARCHAR(36)  NOT NULL,
        internship_id VARCHAR(36)  NOT NULL,
        submitted_by  VARCHAR(20)  NOT NULL DEFAULT 'student',
        rating        INT          NOT NULL CHECK (rating BETWEEN 1 AND 5),
        comments      TEXT,
        submitted_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (student_id)    REFERENCES students(id)    ON DELETE CASCADE,
        FOREIGN KEY (sme_id)        REFERENCES smes(id)        ON DELETE CASCADE,
        FOREIGN KEY (internship_id) REFERENCES internships(id) ON DELETE CASCADE,
        INDEX idx_feedback_internship (internship_id),
        INDEX idx_feedback_student    (student_id)
    ) ENGINE=InnoDB;
    """,
]


def init_db():
    """Run CREATE TABLE IF NOT EXISTS for every table. Called once at startup."""
    conn = get_db_connection()
    if conn is None:
        print("[DB] init_db: could not connect — skipping schema bootstrap.")
        return

    cursor = conn.cursor()
    for sql in CREATE_TABLES_SQL:
        try:
            cursor.execute(sql)
        except Error as e:
            print(f"[DB] init_db error: {e}")
    conn.commit()
    cursor.close()
    conn.close()
    print("[DB] Schema initialised.")
