"""
chains.py
---------
All LLM-driven logic lives here:
  1. extract_job_details  - turn a raw job post into structured JSON
  2. match_resume_to_job   - score a resume against a job + list missing skills
  3. write_email           - generate a personalized, tone-aware cold email

Uses Groq's hosted Llama 3.3 model via langchain_groq, matching the model
already used in the original repo's notebooks. Swap `ChatGroq` for any other
langchain chat model if you'd rather use OpenAI/Anthropic/etc.
"""

import json
from langchain_groq import ChatGroq
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# Available tones the UI lets the user pick from
EMAIL_TONES = {
    "Professional": (
        "Write in a warm, professional, business-appropriate tone. "
        "Confident but not boastful, and easy for a busy recruiter to skim."
    ),
    "Startup": (
        "Write in an energetic, informal startup tone. Show hustle and "
        "genuine excitement about building things fast, while staying credible."
    ),
    "Formal": (
        "Write in a formal, traditional business-letter tone. Precise, "
        "respectful, and free of contractions or casual language."
    ),
    "Concise": (
        "Write as short and to-the-point as possible - no more than 120 words. "
        "Lead with the strongest match, skip pleasantries, end with a clear CTA."
    ),
}


def _get_llm(api_key: str, model: str = "llama-3.3-70b-versatile", temperature: float = 0.3):
    return ChatGroq(groq_api_key=api_key, model=model, temperature=temperature)


def extract_job_details(llm, job_text: str) -> dict:
    """Turn a raw, messy job posting into structured fields."""
    prompt = PromptTemplate.from_template(
        """
        You are given raw, possibly messy text scraped or pasted from a job posting.
        Extract the relevant details and return **valid JSON only**, no preamble,
        with these exact keys:
        - "role": the job title
        - "company": company name if mentioned, else ""
        - "experience": required experience level/years if mentioned, else ""
        - "skills": a JSON list of required technical skills/tools
        - "description": a 2-3 sentence plain-English summary of the role

        RAW JOB POSTING:
        {job_text}
        """
    )
    chain = prompt | llm | JsonOutputParser()
    result = chain.invoke({"job_text": job_text})
    # Normalize in case the model wraps a single job in a list
    if isinstance(result, list):
        result = result[0] if result else {}
    result.setdefault("skills", [])
    return result


def match_resume_to_job(llm, resume_text: str, job_details: dict) -> dict:
    """
    Compare resume text against the extracted job details.
    Returns {"score": int 0-100, "matching_skills": [...], "missing_skills": [...], "summary": str}
    """
    prompt = PromptTemplate.from_template(
        """
        You are an expert technical recruiter. Compare the RESUME below against
        the JOB REQUIREMENTS and return **valid JSON only**, no preamble, with
        these exact keys:
        - "score": integer 0-100 estimating how well the resume matches the job
        - "matching_skills": JSON list of required skills the resume already covers
        - "missing_skills": JSON list of required skills not evidenced in the resume
        - "summary": one or two sentence honest assessment of fit

        JOB ROLE: {role}
        JOB DESCRIPTION: {description}
        REQUIRED SKILLS: {skills}

        RESUME:
        {resume_text}
        """
    )
    chain = prompt | llm | JsonOutputParser()
    result = chain.invoke(
        {
            "role": job_details.get("role", ""),
            "description": job_details.get("description", ""),
            "skills": ", ".join(job_details.get("skills", [])),
            "resume_text": resume_text[:6000],  # keep prompt within a safe size
        }
    )
    result.setdefault("score", 0)
    result.setdefault("matching_skills", [])
    result.setdefault("missing_skills", [])
    result.setdefault("summary", "")
    return result


def write_email(
    llm,
    job_details: dict,
    resume_text: str,
    match_result: dict,
    portfolio_links: list,
    tone: str,
    sender_name: str = "",
) -> str:
    """Generate the final personalized cold email in the requested tone."""
    tone_instruction = EMAIL_TONES.get(tone, EMAIL_TONES["Professional"])

    prompt = PromptTemplate.from_template(
        """
        You are {sender_name_clause} reaching out about the following job opening.
        {tone_instruction}

        Use the RESUME HIGHLIGHTS to personalize the email with genuinely relevant
        experience - don't invent facts that aren't supported by the resume or
        matching skills below. Naturally weave in 1-2 of the PORTFOLIO LINKS if
        they are relevant. Do not mention "missing skills" or the numeric match
        score directly in the email. End with a clear, low-friction call to action.
        Output only the email body (with a subject line on the first line
        prefixed "Subject:"), no extra commentary.

        JOB ROLE: {role}
        COMPANY: {company}
        JOB DESCRIPTION: {description}

        RESUME HIGHLIGHTS (skills that match this job): {matching_skills}
        RESUME TEXT (for context, use selectively): {resume_excerpt}

        PORTFOLIO LINKS: {portfolio_links}
        """
    )
    chain = prompt | llm

    sender_clause = f"{sender_name}, a candidate" if sender_name else "a candidate"

    response = chain.invoke(
        {
            "sender_name_clause": sender_clause,
            "tone_instruction": tone_instruction,
            "role": job_details.get("role", ""),
            "company": job_details.get("company", ""),
            "description": job_details.get("description", ""),
            "matching_skills": ", ".join(match_result.get("matching_skills", [])),
            "resume_excerpt": resume_text[:3000],
            "portfolio_links": ", ".join(portfolio_links) if portfolio_links else "none",
        }
    )
    return response.content
