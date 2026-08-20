"""
main.py
-------
Streamlit web app for the Cold Mail Generator.

Layout (3 tabs):
  ✉️ Generate        — the core email-generation pipeline
  📄 My Resumes      — upload / manage / set-default saved resumes  (auth required)
  📜 History          — browse past generations with charts          (auth required)

Sidebar:
  🔐 Auth widget     — login / sign-up / logout
  ⚙️ Settings        — model picker, API key, sender name

Run with:  streamlit run app/main.py
"""

import os
import streamlit as st
from dotenv import load_dotenv
from langchain_community.document_loaders import WebBaseLoader

from chains import (
    _get_llm, extract_job_details, match_resume_to_job, write_email, EMAIL_TONES,
)
from portfolio import Portfolio
from resume_parser import extract_text_from_pdf
from utils import clean_text

# ── new modules ──
from database import init_db, save_generation
from auth import render_auth_sidebar, is_logged_in, get_current_user
from resume_manager import render_resume_tab, render_resume_selector
from history_dashboard import render_history_tab

load_dotenv()

st.set_page_config(page_title="Cold Mail Generator", page_icon="✉️", layout="wide")

# Create DB tables on first run (idempotent)
init_db()


# ─────────────────────────── helpers ──────────────────────────────────────
def _load_job_text(job_input_mode: str, job_url: str, job_text_area: str) -> str:
    if job_input_mode == "Paste job description":
        return job_text_area
    if not job_url:
        return ""
    loader = WebBaseLoader([job_url])
    docs = loader.load()
    return "\n".join(d.page_content for d in docs)


def _score_color(score: int) -> str:
    if score >= 75:
        return "🟢"
    if score >= 50:
        return "🟡"
    return "🔴"


# ═══════════════════════════  MAIN  ═══════════════════════════════════════
def main():
    st.title("✉️ Cold Mail Generator")
    st.caption(
        "Upload your resume and a job posting to get a match score, missing "
        "skills, and a personalized cold email — powered by Groq LLM."
    )

    # ────────────────────── sidebar ──────────────────────────────
    with st.sidebar:
        # Auth section (login / signup / user badge)
        render_auth_sidebar()

        st.header("⚙️ Settings")
        try:
            api_key = st.secrets.get("GROQ_API_KEY", os.getenv("GROQ_API_KEY", ""))
        except Exception:
            api_key = os.getenv("GROQ_API_KEY", "")
        model = st.selectbox(
            "Model",
            ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"],
            index=0,
            key="sidebar_model",
        )

        # Pre-fill sender name from profile when logged in
        default_name = ""
        if is_logged_in():
            user = get_current_user()
            default_name = user.get("full_name", "") or user.get("username", "")
        sender_name = st.text_input(
            "Your name (used in the email)",
            value=default_name,
            key="sidebar_sender",
        )

        st.divider()
        st.caption("Portfolio source: resource/my_portfolio.csv")

    # ────────────────────── tabs ─────────────────────────────────
    tab_generate, tab_resumes, tab_history = st.tabs(
        ["✉️ Generate", "📄 My Resumes", "📜 History"]
    )

    with tab_generate:
        _render_generate_tab(api_key, model, sender_name)

    with tab_resumes:
        render_resume_tab()

    with tab_history:
        render_history_tab()


# ═══════════════════  GENERATE TAB  ══════════════════════════════════════
def _render_generate_tab(api_key: str, model: str, sender_name: str):
    """The core email-generation pipeline (Step 1 → 5)."""

    # ── Step 1: Job posting ──
    st.subheader("1️⃣ Job Posting")
    job_input_mode = st.radio(
        "How would you like to provide the job posting?",
        ["Paste job description", "Fetch from URL"],
        horizontal=True,
        key="gen_job_mode",
    )
    job_url, job_text_area = "", ""
    if job_input_mode == "Fetch from URL":
        job_url = st.text_input(
            "Job posting URL (e.g. a careers page listing)",
            key="gen_job_url",
        )
    else:
        job_text_area = st.text_area(
            "Paste the job description here", height=200,
            key="gen_job_text",
        )

    # ── Step 2: Resume ──
    st.subheader("2️⃣ Your Resume")
    resume_text, resume_label = render_resume_selector()

    # ── Step 3: Tone ──
    st.subheader("3️⃣ Email Tone")
    tone = st.selectbox("Choose a tone", list(EMAIL_TONES.keys()), key="gen_tone")

    st.divider()
    generate = st.button("🚀 Generate", type="primary",
                         use_container_width=True, key="gen_btn")

    if not generate:
        return

    # ────────────── guards ──────────────
    if not api_key:
        st.error("Groq API key is not configured.")
        st.info("Add `GROQ_API_KEY` to Streamlit Secrets or a `.env` file.")
        return
    if job_input_mode == "Paste job description" and not job_text_area.strip():
        st.error("Please paste a job description.")
        return
    if job_input_mode == "Fetch from URL" and not job_url.strip():
        st.error("Please enter a job posting URL.")
        return
    if resume_text is None or not resume_text.strip():
        st.error("Please upload or select a resume.")
        return

    llm = _get_llm(api_key=api_key, model=model)

    # ────────────── pipeline ──────────────
    with st.spinner("Reading job posting…"):
        try:
            raw_job_text = _load_job_text(job_input_mode, job_url, job_text_area)
            raw_job_text = clean_text(raw_job_text)
        except Exception as e:
            st.error(f"Couldn't load the job posting: {e}")
            return

    with st.spinner("Extracting job requirements…"):
        try:
            job_details = extract_job_details(llm, raw_job_text)
        except Exception as e:
            st.error(f"Couldn't parse the job posting: {e}")
            return

    with st.spinner("Scoring resume against job…"):
        try:
            match_result = match_resume_to_job(llm, resume_text, job_details)
        except Exception as e:
            st.error(f"Couldn't compute the match score: {e}")
            return

    with st.spinner("Finding relevant portfolio links…"):
        try:
            portfolio = Portfolio()
            portfolio_links = portfolio.query_links(job_details.get("skills", []))
        except Exception:
            portfolio_links = []

    with st.spinner(f"Writing your {tone.lower()} email…"):
        try:
            email_text = write_email(
                llm, job_details, resume_text, match_result,
                portfolio_links, tone, sender_name,
            )
        except Exception as e:
            st.error(f"Couldn't generate the email: {e}")
            return

    # ────────────── output ──────────────
    st.divider()
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📋 Job Summary")
        st.markdown(f"**Role:** {job_details.get('role', 'N/A')}")
        if job_details.get("company"):
            st.markdown(f"**Company:** {job_details['company']}")
        if job_details.get("experience"):
            st.markdown(f"**Experience:** {job_details['experience']}")
        st.markdown(f"**Description:** {job_details.get('description', 'N/A')}")
        if job_details.get("skills"):
            st.markdown("**Required Skills:** " + ", ".join(job_details["skills"]))

    with col2:
        score = int(match_result.get("score", 0))
        st.subheader(f"{_score_color(score)} Resume-Job Match: {score}/100")
        st.progress(score / 100)
        if match_result.get("summary"):
            st.markdown(f"_{match_result['summary']}_")
        if match_result.get("matching_skills"):
            st.markdown(
                "**✅ Matching skills:** " + ", ".join(match_result["matching_skills"])
            )
        if match_result.get("missing_skills"):
            st.markdown(
                "**⚠️ Missing skills:** " + ", ".join(match_result["missing_skills"])
            )

    

    st.divider()
    st.subheader(f"✉️ Your {tone} Cold Email")
    st.text_area("Generated email", value=email_text, height=350, key="gen_email_out")
    st.download_button(
        "⬇️ Download email as .txt",
        data=email_text,
        file_name="cold_email.txt",
        mime="text/plain",
        key="gen_download",
    )

    # ────────────── persist to history (logged-in users) ──────────────
    if is_logged_in():
        try:
            user = get_current_user()
            save_generation(
                user_id=user["id"],
                company_name=job_details.get("company", ""),
                job_title=job_details.get("role", ""),
                job_url=job_url,
                job_description=job_details.get("description", ""),
                match_score=int(match_result.get("score", 0)),
                matching_skills=match_result.get("matching_skills", []),
                missing_skills=match_result.get("missing_skills", []),
                email_tone=tone,
                generated_email=email_text,
                portfolio_links=portfolio_links,
            )
            st.success("✅ Generation saved to your history!")
        except Exception:
            pass  # non-critical — don't block the user
    else:
        st.caption("💡 Log in to save this generation and track your history.")


if __name__ == "__main__":
    main()
