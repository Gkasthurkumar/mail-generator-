"""
history_dashboard.py
--------------------
Streamlit UI for the **📜 History & Past Emails** tab.

Features
~~~~~~~~
* Filter by company name and date range.
* Expandable cards for each generation showing full details.
* Copy / download generated emails.
* Match-score trend chart and top-missing-skills bar chart.
"""

from collections import Counter
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from auth import is_logged_in, get_current_user
from database import get_user_history


# ═══════════════════════  TAB: History & Past Emails  ═════════════════════
def render_history_tab():
    """Render the full **📜 History** dashboard."""
    if not is_logged_in():
        st.info("🔒 Please **log in** to view your generation history.")
        return

    user = get_current_user()
    user_id = user["id"]

    st.header("📜 History & Past Emails")
    st.caption("Browse, filter, and re-use your previously generated cold emails.")

    # ────────────── filters ──────────────
    fcol1, fcol2, fcol3 = st.columns([2, 1, 1])
    with fcol1:
        company_q = st.text_input(
            "🔍 Filter by company name",
            key="hist_company",
            placeholder="e.g. Google",
        )
    with fcol2:
        date_from = st.date_input(
            "From date",
            value=datetime.now(timezone.utc).date() - timedelta(days=90),
            key="hist_from",
        )
    with fcol3:
        date_to = st.date_input(
            "To date",
            value=datetime.now(timezone.utc).date(),
            key="hist_to",
        )

    # Convert date objects to datetime for the query
    dt_from = datetime(date_from.year, date_from.month, date_from.day,
                       tzinfo=timezone.utc) if date_from else None
    dt_to   = datetime(date_to.year, date_to.month, date_to.day,
                       tzinfo=timezone.utc) if date_to else None

    history = get_user_history(
        user_id,
        company_filter=company_q.strip(),
        date_from=dt_from,
        date_to=dt_to,
    )

    if not history:
        st.info("No generation history found. Generate your first cold email in the **✉️ Generate** tab!")
        return

    st.markdown(f"**{len(history)}** generation(s) found")

    # ────────────── analytics charts ──────────────
    _render_charts(history)

    st.divider()

    # ────────────── history cards ──────────────
    for idx, h in enumerate(history):
        score = h["match_score"]
        emoji = "🟢" if score >= 75 else ("🟡" if score >= 50 else "🔴")
        date_str = (h["created_at"].strftime("%b %d, %Y  %H:%M")
                    if h["created_at"] else "N/A")

        header = (
            f"{emoji} **{h['company_name'] or 'Unknown Company'}** — "
            f"{h['job_title'] or 'Unknown Role'}  |  "
            f"Score: {score}/100  |  Tone: {h['email_tone']}  |  {date_str}"
        )

        with st.expander(header, expanded=False):
            # ── meta row ──
            mc1, mc2 = st.columns(2)
            with mc1:
                st.markdown(f"**Company:** {h['company_name'] or '—'}")
                st.markdown(f"**Role:** {h['job_title'] or '—'}")
                if h["job_url"]:
                    st.markdown(f"**URL:** [{h['job_url'][:60]}...]({h['job_url']})"
                                if len(h["job_url"]) > 60
                                else f"**URL:** [{h['job_url']}]({h['job_url']})")
            with mc2:
                st.markdown(f"**Match Score:** {emoji} {score}/100")
                st.progress(score / 100)
                st.markdown(f"**Tone:** {h['email_tone']}")

            # ── skills ──
            if h["matching_skills"]:
                st.markdown("**✅ Matching Skills:** " + ", ".join(
                    f"`{s}`" for s in h["matching_skills"]
                ))
            if h["missing_skills"]:
                st.markdown("**⚠️ Missing Skills:** " + ", ".join(
                    f"`{s}`" for s in h["missing_skills"]
                ))

            # ── portfolio links ──
            if h["portfolio_links"]:
                st.markdown("**🔗 Portfolio Links:** " + ", ".join(h["portfolio_links"]))

            # ── job description ──
            if h["job_description"]:
                st.markdown("**📋 Job Description:**")
                with st.container(height=150):
                    st.text(h["job_description"])

            # ── generated email ──
            st.markdown("---")
            st.markdown("**✉️ Generated Email:**")
            st.code(h["generated_email"], language=None)

            # ── actions ──
            dl_col, _ = st.columns([1, 3])
            with dl_col:
                filename = (
                    f"cold_email_{h['company_name'] or 'unknown'}"
                    f"_{h['job_title'] or 'role'}.txt"
                ).replace(" ", "_").lower()
                st.download_button(
                    "⬇️ Download Email",
                    data=h["generated_email"],
                    file_name=filename,
                    mime="text/plain",
                    key=f"dl_{h['id']}_{idx}",
                    use_container_width=True,
                )


# ──────────────────────── chart helpers ───────────────────────────────────
def _render_charts(history: list[dict]):
    """Render analytics charts: score trend + missing skills frequency."""
    if len(history) < 1:
        return

    chart_tab1, chart_tab2 = st.tabs(["📈 Score Trend", "🧩 Skill Gaps"])

    with chart_tab1:
        _render_score_trend(history)

    with chart_tab2:
        _render_skill_gaps(history)


def _render_score_trend(history: list[dict]):
    """Line chart of match scores over time."""
    rows = []
    for h in reversed(history):      # oldest first for x-axis
        rows.append({
            "Date": (h["created_at"].strftime("%Y-%m-%d %H:%M")
                     if h["created_at"] else ""),
            "Company": h["company_name"] or "Unknown",
            "Score": h["match_score"],
        })

    if not rows:
        st.caption("Not enough data for a chart.")
        return

    df = pd.DataFrame(rows)
    st.markdown("**Match Score Over Time**")
    st.line_chart(df, x="Date", y="Score", height=300)

    # Quick stats
    scores = [r["Score"] for r in rows]
    avg = sum(scores) / len(scores)
    best = max(scores)
    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("Average Score", f"{avg:.0f}/100")
    sc2.metric("Best Score", f"{best}/100")
    sc3.metric("Total Generations", len(scores))


def _render_skill_gaps(history: list[dict]):
    """Bar chart of the most commonly missing skills."""
    counter: Counter = Counter()
    for h in history:
        for skill in h.get("missing_skills", []):
            counter[skill.strip()] += 1

    if not counter:
        st.info("No missing skills recorded yet — great match history! 🎉")
        return

    top = counter.most_common(15)
    df = pd.DataFrame(top, columns=["Skill", "Times Missing"])

    st.markdown("**Most Frequently Missing Skills** (across all generations)")
    st.bar_chart(df, x="Skill", y="Times Missing", height=350)

    st.caption(
        "💡 Focus on learning the skills that appear most often to boost "
        "your future match scores."
    )
