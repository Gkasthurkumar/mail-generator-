"""
auth.py
-------
User authentication helpers and the Streamlit sidebar auth widget.

* Passwords hashed with **bcrypt** (salted, adaptive cost).
* Session persisted in ``st.session_state["user"]`` (dict or None).
"""

import bcrypt
import streamlit as st

from database import create_user, get_user_by_username


# ────────────────────── password helpers ──────────────────────────────────
def hash_password(password: str) -> str:
    """Return a bcrypt hash (UTF-8 string) for *password*."""
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Check *password* against a stored bcrypt *password_hash*."""
    return bcrypt.checkpw(
        password.encode("utf-8"), password_hash.encode("utf-8")
    )


# ────────────────────── session helpers ───────────────────────────────────
def _init_session():
    """Ensure session-state keys exist."""
    if "user" not in st.session_state:
        st.session_state["user"] = None


def is_logged_in() -> bool:
    _init_session()
    return st.session_state["user"] is not None


def get_current_user() -> dict | None:
    """Return the logged-in user dict, or None."""
    _init_session()
    return st.session_state["user"]


def logout():
    """Clear the current session."""
    st.session_state["user"] = None


# ────────────────────── core auth actions ─────────────────────────────────
def login(username: str, password: str) -> tuple[bool, str]:
    """
    Validate credentials.
    Returns ``(True, "")`` on success or ``(False, error_message)`` on failure.
    Sets ``st.session_state["user"]`` on success.
    """
    if not username or not password:
        return False, "Please enter both username and password."

    user = get_user_by_username(username)
    if user is None:
        return False, "Username not found. Please sign up first."

    if not verify_password(password, user["password_hash"]):
        return False, "Incorrect password. Please try again."

    # Strip the hash before storing in session for safety
    safe_user = {k: v for k, v in user.items() if k != "password_hash"}
    st.session_state["user"] = safe_user
    return True, ""


def signup(username: str, email: str, password: str,
           confirm_password: str, full_name: str = "") -> tuple[bool, str]:
    """
    Register a new account.
    Returns ``(True, "")`` on success or ``(False, error_message)`` on failure.
    Automatically logs the user in on success.
    """
    # ── validation ──
    if not username or not email or not password:
        return False, "All fields are required."
    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if "@" not in email or "." not in email:
        return False, "Please enter a valid email address."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if password != confirm_password:
        return False, "Passwords do not match."

    pw_hash = hash_password(password)
    user = create_user(username, email, pw_hash, full_name)
    if user is None:
        return False, "Username or email already taken."

    # Auto-login after signup
    safe_user = {k: v for k, v in user.items() if k != "password_hash"}
    st.session_state["user"] = safe_user
    return True, ""


# ────────────────────── sidebar widget ────────────────────────────────────
def render_auth_sidebar():
    """
    Render the authentication section in ``st.sidebar``.

    * Logged in  → user badge + logout button
    * Logged out → tabbed login / sign-up forms
    """
    _init_session()

    with st.sidebar:
        st.markdown("---")

        if is_logged_in():
            user = get_current_user()
            display = user.get("full_name") or user["username"]
            st.markdown(f"### 👤 {display}")
            st.caption(f"@{user['username']}  ·  {user.get('email', '')}")
            if st.button("🚪 Logout", key="btn_logout", use_container_width=True):
                logout()
                st.rerun()
        else:
            st.subheader("🔐 Account")
            mode = st.radio(
                "auth_mode_label",
                ["Login", "Sign Up"],
                horizontal=True,
                key="auth_mode",
                label_visibility="collapsed",
            )
            if mode == "Login":
                _render_login_form()
            else:
                _render_signup_form()

        st.markdown("---")


def _render_login_form():
    """Login form inside ``st.sidebar``."""
    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("Username", key="login_user")
        password = st.text_input("Password", type="password", key="login_pass")
        submitted = st.form_submit_button(
            "🔑 Login", use_container_width=True
        )
    if submitted:
        ok, msg = login(username, password)
        if ok:
            st.toast("Welcome back! 👋", icon="✅")
            st.rerun()
        else:
            st.error(msg)


def _render_signup_form():
    """Sign-up form inside ``st.sidebar``."""
    with st.form("signup_form", clear_on_submit=False):
        full_name = st.text_input("Full name", key="signup_name")
        username  = st.text_input("Username", key="signup_user")
        email     = st.text_input("Email", key="signup_email")
        password  = st.text_input("Password", type="password", key="signup_pass")
        confirm   = st.text_input("Confirm password", type="password",
                                   key="signup_confirm")
        submitted = st.form_submit_button(
            "🚀 Create Account", use_container_width=True
        )
    if submitted:
        ok, msg = signup(username, email, password, confirm, full_name)
        if ok:
            st.toast("Account created! You're now logged in 🎉", icon="✅")
            st.rerun()
        else:
            st.error(msg)
