import streamlit as st
import os
DEBUG = os.getenv("DEBUG", False)

if st.experimental_user.is_logged_in:
    pass
else:
    st.login()

st.title(st.experimental_user.name)

user = st.experimental_user

cols = st.columns([1, 3])   
with cols[0]:
    st.image(user.picture)

with cols[1]:
    st.write(f"{user.email}")
    if user.email_verified:
        st.write("✅ email verified")
    else:
        st.write("❌ email not verified")

st.write(f"Role: {user.role}")

if st.button("Logout"):
    st.logout()

if DEBUG:
    st.sidebar.write(user)
