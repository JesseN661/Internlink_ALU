"""
utils/matching.py
-----------------
Skill-based internship matching engine for InternLink.

Algorithm
---------
1. Parse student skills and internship required skills into normalised sets.
2. Base score = matched_required / total_required × 100
3. Preference boost = +5 pts per matching preference keyword (capped at +15).
4. Optional fuzzy matching via difflib catches near-misses.
5. Return internships scoring >= MATCH_THRESHOLD, sorted descending.
"""

import difflib
from config import active_config

# ── Pull tuneable values from config ─────────────────────────────────────────
MATCH_THRESHOLD = active_config.MATCH_THRESHOLD
FUZZY_ENABLED   = active_config.FUZZY_ENABLED
FUZZY_CUTOFF    = active_config.FUZZY_CUTOFF
PREF_BOOST      = active_config.PREF_BOOST
MAX_PREF_BOOST  = active_config.MAX_PREF_BOOST


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_skills(raw: str | None) -> list[str]:
    """Split comma-separated skill string into normalised list."""
    if not raw:
        return []
    return [s.strip().lower() for s in raw.split(",") if s.strip()]


def _fuzzy_match(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, a, b).ratio() >= FUZZY_CUTOFF


def _skill_covered(student_skill: str, required_skills: list[str]) -> bool:
    if student_skill in required_skills:
        return True
    if FUZZY_ENABLED:
        return any(_fuzzy_match(student_skill, r) for r in required_skills)
    return False


def _count_covered(student_skills: list[str], required_skills: list[str]) -> int:
    """Count how many required skills the student covers."""
    return sum(
        1 for req in required_skills
        if any(_skill_covered(s, [req]) for s in student_skills)
    )


def _preference_boost(preferences: list[str], internship: dict) -> float:
    if not preferences:
        return 0.0
    text = " ".join([
        internship.get("title")       or "",
        internship.get("description") or "",
        internship.get("location")    or "",
    ]).lower()
    boost = sum(PREF_BOOST for p in preferences if p in text)
    return min(boost, MAX_PREF_BOOST)


# ── Public API ────────────────────────────────────────────────────────────────

def compute_match_score(student_skills_raw: str | None,
                        internship_skills_raw: str | None) -> float:
    """Return a 0–100 match score between a student and one internship."""
    student_skills  = _parse_skills(student_skills_raw)
    required_skills = _parse_skills(internship_skills_raw)
    if not required_skills:
        return 0.0
    covered = _count_covered(student_skills, required_skills)
    return round((covered / len(required_skills)) * 100, 2)


def match_student_to_internships(student: dict,
                                 internships: list[dict]) -> list[dict]:
    """
    Score and rank internships for a student.

    Returns list of dicts with keys:
        internship, score, matched_skills, missing_skills
    Sorted by score descending. Only includes scores >= MATCH_THRESHOLD.
    """
    student_skills = _parse_skills(student.get("skills"))
    preferences    = _parse_skills(student.get("preferences"))
    results        = []

    for internship in internships:
        if not internship.get("is_active", True):
            continue

        required_skills = _parse_skills(internship.get("skills_required"))
        if not required_skills:
            continue

        covered    = _count_covered(student_skills, required_skills)
        base_score = (covered / len(required_skills)) * 100
        boost      = _preference_boost(preferences, internship)
        final      = min(round(base_score + boost, 2), 100.0)

        if final < MATCH_THRESHOLD:
            continue

        matched = [r for r in required_skills
                   if any(_skill_covered(s, [r]) for s in student_skills)]
        missing = [r for r in required_skills if r not in matched]

        results.append({
            "internship":     internship,
            "score":          final,
            "matched_skills": matched,
            "missing_skills": missing,
        })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def get_recommendations_for_student(student: dict, db_conn) -> list[dict]:
    """Fetch all active internships from DB and return matched results."""
    cursor = db_conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT i.*, s.company_name
        FROM   internships i
        JOIN   smes s ON s.id = i.sme_id
        WHERE  i.is_active = TRUE
        ORDER  BY i.created_at DESC
        """
    )
    internships = cursor.fetchall()
    cursor.close()
    return match_student_to_internships(student, internships)
