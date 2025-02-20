import streamlit as st
import os
import logging

# Configure debug settings
DEBUG = bool(st.secrets.get("DEBUG", False))
if DEBUG:
    logging.getLogger("watchdog").setLevel(logging.INFO)
    logging.basicConfig(level=logging.DEBUG)
    st.write("Debug mode enabled")
    

# Retrieve access token from environment variable
ACCESS_TOKEN = os.getenv("MGMT_API_ACCESS_TOKEN")

upload_page = st.Page(
    "src/classroom-transcripts/upload.py",
    title="Upload Audio",
    icon="📤",
    url_path="/upload",
    default=True,
)
list_page = st.Page(
    "src/classroom-transcripts/transcript_list_view.py",
    title="Transcripts",
    icon="🎙️",
    url_path="/transcripts",
)

# Build pages list based on debug setting
pages_list = [upload_page]

if st.experimental_user.get("is_logged_in"):
    user = st.experimental_user    # pages_list.append(profile_page)
    pages_list.append(list_page)
    with st.sidebar:
        cols = st.columns([1, 3])
        with cols[0]:
            if user.get("picture"):
                st.image(str(user.get("picture")))
        with cols[1]:
            st.write(str(user.get("name", "")))
            email_display = f"{user.get('email')} ✓" if user.get('email_verified') else "Email not verified."
            st.write(email_display)
        if st.button("Logout"):
            st.logout()
        if DEBUG:
            st.write(user)

pages = st.navigation(pages_list)
pages.run()
