"""
database.py
-----------
SQLite database engine, session management, and all CRUD operations.

The SQLite file lives at ``app/data/coldmail.db`` and is created
automatically on first run via ``init_db()``.
"""

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from models import Base, User, UserResume, GenerationHistory

# ───────────────────────────── paths & engine ─────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.join(_BASE_DIR, "data")
os.makedirs(_DATA_DIR, exist_ok=True)

_DB_PATH = os.path.join(_DATA_DIR, "coldmail.db")
_DATABASE_URL = f"sqlite:///{_DB_PATH}"

_engine = None
_SessionFactory = None


def get_engine():
    """Return a singleton SQLAlchemy engine (thread-safe for SQLite)."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            _DATABASE_URL,
            connect_args={"check_same_thread": False},
            echo=False,
        )
    return _engine


def init_db():
    """Create all tables if they don't already exist."""
    engine = get_engine()
    Base.metadata.create_all(engine)


@contextmanager
def get_session():
    """Yield a scoped SQLAlchemy session; auto-commits or rolls back."""
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine())
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ──────────────────────── helper converters ────────────────────────────────
def _user_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "password_hash": u.password_hash,
        "full_name": u.full_name or "",
        "created_at": u.created_at,
    }


def _resume_to_dict(r: UserResume) -> dict:
    return {
        "id": r.id,
        "user_id": r.user_id,
        "resume_title": r.resume_title,
        "resume_text": r.resume_text,
        "parsed_skills": json.loads(r.parsed_skills or "[]"),
        "is_default": r.is_default,
        "uploaded_at": r.uploaded_at,
    }


def _history_to_dict(h: GenerationHistory) -> dict:
    return {
        "id": h.id,
        "user_id": h.user_id,
        "company_name": h.company_name,
        "job_title": h.job_title,
        "job_url": h.job_url,
        "job_description": h.job_description,
        "match_score": h.match_score,
        "matching_skills": json.loads(h.matching_skills or "[]"),
        "missing_skills": json.loads(h.missing_skills or "[]"),
        "email_tone": h.email_tone,
        "generated_email": h.generated_email,
        "portfolio_links": json.loads(h.portfolio_links or "[]"),
        "created_at": h.created_at,
    }


# ═══════════════════════════  USER CRUD  ══════════════════════════════════
def create_user(username: str, email: str, password_hash: str,
                full_name: str = "") -> dict | None:
    """Create a new user.  Returns user dict on success, None if duplicate."""
    with get_session() as s:
        user = User(
            username=username.strip().lower(),
            email=email.strip().lower(),
            password_hash=password_hash,
            full_name=full_name.strip(),
        )
        try:
            s.add(user)
            s.flush()                       # populate user.id
            return _user_to_dict(user)
        except IntegrityError:
            s.rollback()
            return None


def get_user_by_username(username: str) -> dict | None:
    """Look up a user by username (case-insensitive)."""
    with get_session() as s:
        user = (s.query(User)
                .filter(User.username == username.strip().lower())
                .first())
        return _user_to_dict(user) if user else None


def get_user_by_email(email: str) -> dict | None:
    """Look up a user by email (case-insensitive)."""
    with get_session() as s:
        user = (s.query(User)
                .filter(User.email == email.strip().lower())
                .first())
        return _user_to_dict(user) if user else None


# ═══════════════════════════  RESUME CRUD  ════════════════════════════════
def save_resume(user_id: int, resume_title: str, resume_text: str,
                parsed_skills: list | None = None,
                is_default: bool = False) -> dict:
    """Save a resume.  If *is_default*, clears other defaults first."""
    skills_json = json.dumps(parsed_skills or [])
    with get_session() as s:
        if is_default:
            s.query(UserResume).filter(
                UserResume.user_id == user_id,
                UserResume.is_default == True,          # noqa: E712
            ).update({"is_default": False})
        resume = UserResume(
            user_id=user_id,
            resume_title=resume_title.strip(),
            resume_text=resume_text,
            parsed_skills=skills_json,
            is_default=is_default,
        )
        s.add(resume)
        s.flush()
        return _resume_to_dict(resume)


def get_user_resumes(user_id: int) -> list[dict]:
    """Return all resumes for a user, newest first."""
    with get_session() as s:
        rows = (s.query(UserResume)
                .filter(UserResume.user_id == user_id)
                .order_by(UserResume.uploaded_at.desc())
                .all())
        return [_resume_to_dict(r) for r in rows]


def get_default_resume(user_id: int) -> dict | None:
    """Return the user's default resume, or None."""
    with get_session() as s:
        r = (s.query(UserResume)
             .filter(UserResume.user_id == user_id,
                     UserResume.is_default == True)     # noqa: E712
             .first())
        return _resume_to_dict(r) if r else None


def set_default_resume(user_id: int, resume_id: int) -> bool:
    """Mark *resume_id* as default and clear others.  Returns success."""
    with get_session() as s:
        s.query(UserResume).filter(
            UserResume.user_id == user_id,
            UserResume.is_default == True,              # noqa: E712
        ).update({"is_default": False})
        count = (s.query(UserResume)
                 .filter(UserResume.id == resume_id,
                         UserResume.user_id == user_id)
                 .update({"is_default": True}))
        return count > 0


def delete_resume(resume_id: int, user_id: int) -> bool:
    """Delete a resume by ID (scoped to *user_id* for safety)."""
    with get_session() as s:
        count = (s.query(UserResume)
                 .filter(UserResume.id == resume_id,
                         UserResume.user_id == user_id)
                 .delete())
        return count > 0


# ═══════════════════════════  HISTORY CRUD  ═══════════════════════════════
def save_generation(
    user_id: int,
    company_name: str,
    job_title: str,
    job_url: str,
    job_description: str,
    match_score: int,
    matching_skills: list,
    missing_skills: list,
    email_tone: str,
    generated_email: str,
    portfolio_links: list,
) -> dict:
    """Persist one cold-email generation record."""
    with get_session() as s:
        entry = GenerationHistory(
            user_id=user_id,
            company_name=company_name,
            job_title=job_title,
            job_url=job_url,
            job_description=job_description,
            match_score=match_score,
            matching_skills=json.dumps(matching_skills or []),
            missing_skills=json.dumps(missing_skills or []),
            email_tone=email_tone,
            generated_email=generated_email,
            portfolio_links=json.dumps(portfolio_links or []),
        )
        s.add(entry)
        s.flush()
        return _history_to_dict(entry)


def get_user_history(
    user_id: int,
    company_filter: str = "",
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[dict]:
    """Return generation history with optional company & date filters."""
    with get_session() as s:
        q = s.query(GenerationHistory).filter(
            GenerationHistory.user_id == user_id
        )
        if company_filter:
            q = q.filter(
                GenerationHistory.company_name.ilike(f"%{company_filter}%")
            )
        if date_from:
            q = q.filter(GenerationHistory.created_at >= date_from)
        if date_to:
            # Include the full end-day
            end = datetime(date_to.year, date_to.month, date_to.day,
                           23, 59, 59, tzinfo=timezone.utc)
            q = q.filter(GenerationHistory.created_at <= end)
        rows = q.order_by(GenerationHistory.created_at.desc()).all()
        return [_history_to_dict(h) for h in rows]


def get_history_by_id(history_id: int) -> dict | None:
    """Fetch a single history entry."""
    with get_session() as s:
        h = s.query(GenerationHistory).filter(
            GenerationHistory.id == history_id
        ).first()
        return _history_to_dict(h) if h else None
