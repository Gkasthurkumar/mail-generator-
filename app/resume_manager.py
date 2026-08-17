"""
resume_manager.py
-----------------
Streamlit UI for the **📄 My Resumes** tab and the resume-selector widget
used inside the Generate tab.

Features
~~~~~~~~
* Upload & save PDFs with automatic skill extraction (keyword-based).
* View / set-default / delete saved resumes.
* In-generate selector: pick a saved resume **or** upload a new one.
"""

import re
import streamlit as st

from auth import is_logged_in, get_current_user
from database import (
    save_resume, get_user_resumes, get_default_resume,
    set_default_resume, delete_resume,
)
from resume_parser import extract_text_from_pdf


# ─────────────────── lightweight skill extractor ──────────────────────────
_COMMON_SKILLS: set[str] = {
    # Programming languages
    "python", "java", "javascript", "typescript", "c++", "c#", "c",
    "go", "golang", "rust", "ruby", "php", "swift", "kotlin", "scala",
    "r", "matlab", "perl", "haskell", "lua", "dart", "elixir",
    # Web frameworks & tools
    "html", "css", "sass", "less", "react", "reactjs", "angular",
    "vue", "vue.js", "vuejs", "svelte", "next.js", "nextjs", "nuxt",
    "node.js", "nodejs", "express", "expressjs", "django", "flask",
    "fastapi", "spring", "spring boot", "springboot", "rails",
    "ruby on rails", "asp.net", ".net", "laravel", "symfony",
    # Mobile
    "react native", "flutter", "swiftui", "jetpack compose", "xamarin",
    # Data & ML
    "sql", "nosql", "mongodb", "postgresql", "mysql", "sqlite", "redis",
    "elasticsearch", "kafka", "spark", "hadoop", "airflow", "hive",
    "cassandra", "dynamodb", "bigquery", "snowflake", "databricks",
    "tensorflow", "pytorch", "scikit-learn", "sklearn", "pandas", "numpy",
    "keras", "opencv", "nltk", "spacy", "hugging face", "transformers",
    "machine learning", "deep learning", "nlp", "computer vision",
    "data science", "data engineering", "data analysis",
    # Cloud & DevOps
    "aws", "azure", "gcp", "google cloud", "docker", "kubernetes", "k8s",
    "terraform", "ansible", "jenkins", "github actions", "ci/cd", "cicd",
    "cloudformation", "pulumi", "helm", "istio",
    # Tools & practices
    "git", "github", "gitlab", "bitbucket", "linux", "unix", "bash",
    "powershell", "jira", "confluence", "agile", "scrum", "kanban",
    "rest", "restful", "graphql", "grpc", "websocket", "microservices",
    "api", "oauth", "jwt",
    # Other
    "figma", "tableau", "power bi", "excel", "sap",
}

# Build regex patterns once for multi-word skills first, then singles
_MULTI_WORD = sorted(
    [s for s in _COMMON_SKILLS if " " in s or "." in s],
    key=len, reverse=True,
)
_SINGLE_WORD = sorted(
    [s for s in _COMMON_SKILLS if " " not in s and "." not in s],
)


def extract_skills_from_text(text: str) -> list[str]:
    """
    Fast keyword-based skill extraction (no LLM needed).
    Returns a sorted, de-duplicated list of recognised skills.
    """
    lower = text.lower()
    found: set[str] = set()

    # Multi-word / dotted skills (case-insensitive substring)
    for skill in _MULTI_WORD:
        if skill in lower:
            found.add(skill.title() if len(skill) > 3 else skill.upper())

    # Single-word skills (word-boundary aware)
    for skill in _SINGLE_WORD:
        pattern = rf"\b{re.escape(skill)}\b"
        if re.search(pattern, lower):
            # Capitalise short acronyms, title-case the rest
            if len(skill) <= 3 and skill.isalpha():
                found.add(skill.upper())
            else:
                found.add(skill.title())

    return sorted(found)


# ═════════════════════════  TAB: My Resumes  ══════════════════════════════
def render_resume_tab():
    """Render the full **📄 My Resumes** management page."""
    if not is_logged_in():
        st.info("🔒 Please **log in** to manage your saved resumes.")
        return

    user = get_current_user()
    user_id = user["id"]

    st.header("📄 My Resumes")
    st.caption("Upload, manage, and set a default resume for quick email generation.")

    # ────────────── upload section ──────────────
    st.subheader("Upload New Resume")
    with st.form("upload_resume_form", clear_on_submit=True):
        title = st.text_input(
            "Resume title (e.g. 'SDE Resume 2026')",
            key="new_resume_title",
        )
        pdf = st.file_uploader("Choose a PDF file", type=["pdf"], key="new_resume_pdf")
        make_default = st.checkbox("Set as default resume", value=True, key="new_resume_default")
        submitted = st.form_submit_button("📤 Upload & Save", use_container_width=True)

    if submitted:
        if not pdf:
            st.error("Please select a PDF file.")
        elif not title.strip():
            st.error("Please give this resume a title.")
        else:
            with st.spinner("Extracting text & skills…"):
                text = extract_text_from_pdf(pdf)
                if not text.strip():
                    st.error("Couldn't extract text from that PDF. Is it a scanned image?")
                else:
                    skills = extract_skills_from_text(text)
                    save_resume(
                        user_id=user_id,
                        resume_title=title.strip(),
                        resume_text=text,
                        parsed_skills=skills,
                        is_default=make_default,
                    )
                    st.toast("Resume saved! ✅", icon="📄")
                    st.rerun()

    # ────────────── saved resumes list ──────────────
    st.divider()
    st.subheader("Saved Resumes")
    resumes = get_user_resumes(user_id)

    if not resumes:
        st.info("You haven't saved any resumes yet. Upload one above ☝️")
        return

    for idx, r in enumerate(resumes):
        default_badge = " ⭐ **Default**" if r["is_default"] else ""
        with st.expander(f"📄 {r['resume_title']}{default_badge}  —  "
                         f"Uploaded {r['uploaded_at'].strftime('%b %d, %Y') if r['uploaded_at'] else 'N/A'}"):
            # Skills
            if r["parsed_skills"]:
                st.markdown("**Extracted Skills:**")
                skill_tags = "  ".join(
                    f"`{s}`" for s in r["parsed_skills"]
                )
                st.markdown(skill_tags)
            else:
                st.caption("No skills extracted.")

            # Resume text preview
            st.markdown("**Resume Text Preview:**")
            preview = r["resume_text"][:800]
            if len(r["resume_text"]) > 800:
                preview += "…"
            st.text(preview)

            # Actions
            col_a, col_b = st.columns(2)
            with col_a:
                if not r["is_default"]:
                    if st.button("⭐ Set as Default", key=f"def_{r['id']}_{idx}",
                                 use_container_width=True):
                        set_default_resume(user_id, r["id"])
                        st.toast(f"'{r['resume_title']}' is now your default!", icon="⭐")
                        st.rerun()
                else:
                    st.success("This is your default resume")
            with col_b:
                if st.button("🗑️ Delete", key=f"del_{r['id']}_{idx}",
                             use_container_width=True):
                    delete_resume(r["id"], user_id)
                    st.toast(f"Deleted '{r['resume_title']}'", icon="🗑️")
                    st.rerun()


# ═══════════════════  WIDGET: Resume Selector (Generate tab)  ═════════════
def render_resume_selector() -> tuple[str | None, str]:
    """
    Render resume-source chooser in the Generate tab.

    Returns
    -------
    (resume_text, resume_title)
        The text to use and its label.  ``resume_text`` is ``None`` when the
        user hasn't provided/selected anything yet.
    """
    if not is_logged_in():
        # Fallback: plain file uploader (guest mode)
        pdf = st.file_uploader("Upload your resume (PDF)", type=["pdf"], key="gen_resume_guest")
        if pdf is not None:
            text = extract_text_from_pdf(pdf)
            return (text, pdf.name) if text.strip() else (None, "")
        return None, ""

    user = get_current_user()
    resumes = get_user_resumes(user["id"])

    if not resumes:
        # User is logged in but has no saved resumes
        pdf = st.file_uploader("Upload your resume (PDF)", type=["pdf"], key="gen_resume_new")
        st.caption("💡 Tip: Save resumes in the **📄 My Resumes** tab for quick access.")
        if pdf is not None:
            text = extract_text_from_pdf(pdf)
            return (text, pdf.name) if text.strip() else (None, "")
        return None, ""

    # User has saved resumes → offer a choice
    source = st.radio(
        "Resume source",
        ["📂 Use saved resume", "📤 Upload new"],
        horizontal=True,
        key="resume_source_radio",
    )

    if source == "📤 Upload new":
        pdf = st.file_uploader("Upload your resume (PDF)", type=["pdf"], key="gen_resume_upload")
        if pdf is not None:
            text = extract_text_from_pdf(pdf)
            return (text, pdf.name) if text.strip() else (None, "")
        return None, ""

    # Saved-resume picker
    default = get_default_resume(user["id"])
    labels = [r["resume_title"] + (" ⭐" if r["is_default"] else "") for r in resumes]
    default_idx = 0
    if default:
        for i, r in enumerate(resumes):
            if r["id"] == default["id"]:
                default_idx = i
                break

    chosen_idx = st.selectbox(
        "Select a saved resume",
        range(len(resumes)),
        index=default_idx,
        format_func=lambda i: labels[i],
        key="gen_resume_select",
    )
    chosen = resumes[chosen_idx]
    return chosen["resume_text"], chosen["resume_title"]
