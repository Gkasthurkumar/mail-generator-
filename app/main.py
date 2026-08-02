"""
main.py
-------
Streamlit web app for the Cold Mail Generator.

Flow:
  1. User pastes a job posting (text or URL) -> LLM extracts structured job details.
  2. User uploads their resume (PDF) -> text extracted.
  3. LLM scores the resume against the job and lists missing skills.
  4. Relevant portfolio links are pulled from ChromaDB based on required skills.
  5. LLM writes a personalized cold email in the tone the user picks.

Run with:  streamlit run app/main.py
"""

import os
import streamlit as st
from dotenv import load_dotenv
from langchain_community.document_loaders import WebBaseLoader

from chains import _get_llm, extract_job_details, match_resume_to_job, write_email, EMAIL_TONES
from portfolio import Portfolio
from resume_parser import extract_text_from_pdf
from utils import clean_text

load_dotenv()

st.set_page_config(page_title="Cold Mail Generator", page_icon="✉️", layout="wide")


def load_job_text(job_input_mode: str, job_url: str, job_text_area: str) -> str:
    if job_input_mode == "Paste job description":
        return job_text_area
    if not job_url:
        return ""
    loader = WebBaseLoader([job_url])
    docs = loader.load()
    return "\n".join(d.page_content for d in docs)


def score_color(score: int) -> str:
    if score >= 75:
        return "🟢"
    if score >= 50:
        return "🟡"
    return "🔴"


def main():
    st.title("✉️ Cold Mail Generator")
    st.caption(
        "Upload your resume and a job posting to get a match score, missing "
        "skills, and a personalized cold email — no notebook required."
    )

    # ---------------------------------------------------------------- Sidebar
    with st.sidebar:
        st.header("Settings")
        api_key = st.secrets.get("GROQ_API_KEY", os.getenv("GROQ_API_KEY", ""))
        model = st.selectbox(
            "Model",
            ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
            index=0,
        )
        sender_name = st.text_input("Your name (optional, used in the email)")
        st.divider()
        st.caption("Portfolio source: resource/my_portfolio.csv")

    # ------------------------------------------------------------- Job input
    st.subheader("1. Job Posting")
    job_input_mode = st.radio(
        "How would you like to provide the job posting?",
        ["Paste job description", "Fetch from URL"],
        horizontal=True,
    )
    job_url, job_text_area = "", ""
    if job_input_mode == "Fetch from URL":
        job_url = st.text_input("Job posting URL (e.g. a careers page listing)")
    else:
        job_text_area = st.text_area("Paste the job description here", height=200)

    # ---------------------------------------------------------- Resume input
    st.subheader("2. Your Resume")
    resume_file = st.file_uploader("Upload your resume (PDF)", type=["pdf"])

    # ------------------------------------------------------------ Tone pick
    st.subheader("3. Email Tone")
    tone = st.selectbox("Choose a tone", list(EMAIL_TONES.keys()))

    st.divider()
    generate = st.button("🚀 Generate", type="primary", use_container_width=True)

    if not generate:
        return

    # -------------------------------------------------------------- Guards
    if not api_key:
        st.error("Groq API key is not configured.")
        st.info("Add GROQ_API_KEY to Streamlit Secrets.")
        return
    if job_input_mode == "Paste job description" and not job_text_area.strip():
        st.error("Please paste a job description.")
        return
    if job_input_mode == "Fetch from URL" and not job_url.strip():
        st.error("Please enter a job posting URL.")
        return
    if resume_file is None:
        st.error("Please upload your resume as a PDF.")
        return

    llm = _get_llm(api_key=api_key, model=model)

    # ------------------------------------------------------------- Pipeline
    with st.spinner("Reading job posting..."):
        try:
            raw_job_text = load_job_text(job_input_mode, job_url, job_text_area)
            raw_job_text = clean_text(raw_job_text)
        except Exception as e:
            st.error(f"Couldn't load the job posting: {e}")
            return

    with st.spinner("Extracting job requirements..."):
        try:
            job_details = extract_job_details(llm, raw_job_text)
        except Exception as e:
            st.error(f"Couldn't parse the job posting: {e}")
            return

    with st.spinner("Reading your resume..."):
        resume_text = extract_text_from_pdf(resume_file)
        if not resume_text.strip():
            st.error("Couldn't extract any text from that PDF. Is it a scanned image?")
            return

    with st.spinner("Scoring resume against job..."):
        try:
            match_result = match_resume_to_job(llm, resume_text, job_details)
        except Exception as e:
            st.error(f"Couldn't compute the match score: {e}")
            return

    with st.spinner("Finding relevant portfolio links..."):
        try:
            portfolio = Portfolio()
            portfolio_links = portfolio.query_links(job_details.get("skills", []))
        except Exception:
            portfolio_links = []

    with st.spinner(f"Writing your {tone.lower()} email..."):
        try:
            email_text = write_email(
                llm, job_details, resume_text, match_result, portfolio_links, tone, sender_name
            )
        except Exception as e:
            st.error(f"Couldn't generate the email: {e}")
            return

    # --------------------------------------------------------------- Output
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
        st.subheader(f"{score_color(score)} Resume-Job Match Score: {score}/100")
        st.progress(score / 100)
        if match_result.get("summary"):
            st.markdown(f"_{match_result['summary']}_")
        if match_result.get("matching_skills"):
            st.markdown("**✅ Matching skills:** " + ", ".join(match_result["matching_skills"]))
        if match_result.get("missing_skills"):
            st.markdown("**⚠️ Missing skills:** " + ", ".join(match_result["missing_skills"]))

    if portfolio_links:
        st.markdown("**🔗 Relevant portfolio links found:** " + ", ".join(portfolio_links))

    st.divider()
    st.subheader(f"✉️ Your {tone} Cold Email")
    st.text_area("Generated email", value=email_text, height=350)
    st.download_button(
        "⬇️ Download email as .txt",
        data=email_text,
        file_name="cold_email.txt",
        mime="text/plain",
    )


if __name__ == "__main__":
    main()
