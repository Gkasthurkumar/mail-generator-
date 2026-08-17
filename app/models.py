"""
models.py
---------
SQLAlchemy ORM models for the Cold Mail Generator.

Tables:
  - User           : registered users with hashed passwords
  - UserResume     : saved PDF resumes with extracted text & skills
  - GenerationHistory : every cold-email generation run
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, func,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _utcnow():
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    username      = Column(String(50),  unique=True, nullable=False, index=True)
    email         = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name     = Column(String(100), nullable=True, default="")
    created_at    = Column(DateTime, default=_utcnow)

    resumes = relationship("UserResume", back_populates="user",
                           cascade="all, delete-orphan", lazy="select")
    history = relationship("GenerationHistory", back_populates="user",
                           cascade="all, delete-orphan", lazy="select")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}')>"


class UserResume(Base):
    __tablename__ = "user_resumes"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    resume_title  = Column(String(200), nullable=False)
    resume_text   = Column(Text, nullable=False, default="")
    parsed_skills = Column(Text, default="[]")      # JSON-encoded list of strings
    is_default    = Column(Boolean, default=False)
    uploaded_at   = Column(DateTime, default=_utcnow)

    user = relationship("User", back_populates="resumes")

    def __repr__(self):
        return f"<UserResume(id={self.id}, title='{self.resume_title}')>"


class GenerationHistory(Base):
    __tablename__ = "generation_history"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_id         = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    company_name    = Column(String(200), default="")
    job_title       = Column(String(200), default="")
    job_url         = Column(String(500), default="")
    job_description = Column(Text, default="")
    match_score     = Column(Integer, default=0)
    matching_skills = Column(Text, default="[]")     # JSON-encoded list
    missing_skills  = Column(Text, default="[]")     # JSON-encoded list
    email_tone      = Column(String(50), default="")
    generated_email = Column(Text, default="")
    portfolio_links = Column(Text, default="[]")     # JSON-encoded list
    created_at      = Column(DateTime, default=_utcnow)

    user = relationship("User", back_populates="history")

    def __repr__(self):
        return (f"<GenerationHistory(id={self.id}, "
                f"company='{self.company_name}', role='{self.job_title}')>")
