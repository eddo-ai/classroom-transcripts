"""Utility script to view Azure Table Storage contents."""

import streamlit as st
from .table_client import get_table_client, list_table_items

# Set environment variables from Streamlit secrets
import os

account_name = st.secrets.get("AZURE_STORAGE_ACCOUNT_NAME")
if account_name is not None:
    os.environ["AZURE_STORAGE_ACCOUNT_NAME"] = account_name

connection_string = st.secrets.get("AZURE_STORAGE_CONNECTION_STRING")
if connection_string is not None:
    os.environ["AZURE_STORAGE_CONNECTION_STRING"] = connection_string
