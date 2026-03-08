"""
config.py
---------
Central configuration for InternLink.
All tuneable constants live here — nothing is scattered across routes.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── Flask ──────────────────────────────────────────────────────────────────
    SECRET_KEY             = os.getenv("SECRET_KEY", "change-me-in-production")
    SESSION_COOKIE_HTTPONLY= True
    SESSION_COOKIE_SAMESITE= "Lax"
    SESSION_COOKIE_SECURE  = os.getenv("FLASK_ENV") == "production"

    # ── Database ───────────────────────────────────────────────────────────────
    DB_HOST     = os.getenv("DB_HOST",     "localhost")
    DB_USER     = os.getenv("DB_USER",     "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME     = os.getenv("DB_NAME",     "internlink")

    # ── File uploads ───────────────────────────────────────────────────────────
    MAX_CONTENT_LENGTH  = 5 * 1024 * 1024   # 5 MB hard limit (Flask enforced)
    UPLOAD_FOLDER       = "uploads"          # relative to app root_path
    ALLOWED_EXTENSIONS  = {"pdf"}

    # ── Matching engine ────────────────────────────────────────────────────────
    MATCH_THRESHOLD  = 70.0   # min score (0–100) to surface a recommendation
    FUZZY_ENABLED    = True
    FUZZY_CUTOFF     = 0.80
    PREF_BOOST       = 5.0
    MAX_PREF_BOOST   = 15.0

    # ── Pagination ─────────────────────────────────────────────────────────────
    INTERNSHIPS_PER_PAGE = 50
    APPLICATIONS_PER_PAGE = 10


class DevelopmentConfig(Config):
    FLASK_DEBUG = True


class ProductionConfig(Config):
    FLASK_DEBUG            = False
    SESSION_COOKIE_SECURE  = True


# Pick config based on FLASK_ENV env var (default: development)
config_map = {
    "development": DevelopmentConfig,
    "production":  ProductionConfig,
}

active_config = config_map.get(os.getenv("FLASK_ENV", "development"), DevelopmentConfig)
