import streamlit as st
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Configure debug settings
DEBUG = bool(os.getenv("DEBUG", "true"))  # Force debug mode temporarily
if DEBUG:
    logging.getLogger("watchdog").setLevel(logging.WARNING)
    logging.basicConfig(level=logging.DEBUG)
    st.write("Debug mode enabled")

upload_page = st.Page(
    "src/upload.py",
    title="Upload Audio",
    icon="📤",
    url_path="/upload",
    default=True,
)
list_page = st.Page(
    "src/transcript_list_view.py",
    title="Transcripts",
    icon="🎙️",
    url_path="/transcripts",
)
detail_page = st.Page(
    "src/transcript_detail_view.py",
    title="Transcript Detail",
    icon="📄",
    url_path="/transcript_detail",
)

# Build pages list based on debug setting
pages_list = [upload_page]

if st.experimental_user.is_logged_in:
    profile_page = st.Page(
        "src/user_profile.py",
        title=st.experimental_user.name,
        icon="👤",
        url_path="/profile",
    )
    pages_list.append(profile_page)
    pages_list.append(list_page)
    pages_list.append(detail_page)
    with st.sidebar:
        cols = st.columns([1, 3])
        with cols[0]:
            st.image(st.experimental_user.picture)
        with cols[1]:
            st.write(st.experimental_user.name)
            st.write(st.experimental_user.email)
            if st.button("Logout"):
                st.logout()

pages = st.navigation(pages_list)
pages.run()
