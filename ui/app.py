import sys
import uuid
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from agent.orchestrator import get_session_history, handle_query, list_sessions
from observability.logger import get_logger

load_dotenv(Path(__file__).parent.parent / ".env")

logger = get_logger(__name__)


def new_session():
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.messages = []


@st.cache_data(ttl=30, show_spinner=False)
def load_sessions() -> list[dict]:
    return list_sessions()


def switch_session(thread_id: str):
    try:
        st.session_state.messages = get_session_history(thread_id)
        st.session_state.thread_id = thread_id
    except Exception:
        logger.exception("Loading session history failed")
        st.session_state.switch_error = f"Could not load session {thread_id}"


def render_sessions():
    st.subheader("Past sessions")
    if error := st.session_state.pop("switch_error", None):
        st.error(error)
    try:
        sessions = load_sessions()
    except Exception:
        logger.exception("Listing sessions failed")
        st.warning("Could not load sessions.")
        return

    if not sessions:
        st.caption("No saved sessions yet.")
        return

    for s in sessions:
        label = s["preview"] or s["thread_id"]
        if len(label) > 40:
            label = label[:40] + "…"
        current = s["thread_id"] == st.session_state.thread_id
        st.button(
            label,
            key=f"session-{s['thread_id']}",
            help=s["thread_id"],
            type="primary" if current else "secondary",
            disabled=current,
            on_click=switch_session,
            args=(s["thread_id"],),
            use_container_width=True,
        )


def render():
    st.set_page_config(page_title="AI Architect", page_icon="🏗️")
    st.title("AI Architect")
    st.caption("Describe a system and let the agent design it for you.")

    if "thread_id" not in st.session_state:
        new_session()

    with st.sidebar:
        st.subheader("Session")
        st.code(st.session_state.thread_id, language=None)
        st.button("New session", on_click=new_session, use_container_width=True)
        st.divider()
        render_sessions()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if question := st.chat_input("Ask a question..."):
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    response = handle_query(question, st.session_state.thread_id)
                except Exception as e:
                    logger.exception("Query failed")
                    st.error(f"Something went wrong: {e}")
                    return
            st.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})
        load_sessions.clear()
        st.rerun()


def main():
    """Console entry point: launches the Streamlit server for this app."""
    from streamlit.web import cli as stcli

    sys.argv = ["streamlit", "run", str(Path(__file__).resolve()), *sys.argv[1:]]
    sys.exit(stcli.main())


if __name__ == "__main__":
    render()
