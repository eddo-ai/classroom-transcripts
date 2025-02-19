"""Utility script to view Azure Table Storage contents."""

import streamlit as st
from .table_client import get_table_client

# Set environment variables from Streamlit secrets
import os

account_name = st.secrets.get("AZURE_STORAGE_ACCOUNT_NAME")
if account_name is not None:
    os.environ["AZURE_STORAGE_ACCOUNT_NAME"] = account_name

connection_string = st.secrets.get("AZURE_STORAGE_CONNECTION_STRING")
if connection_string is not None:
    os.environ["AZURE_STORAGE_CONNECTION_STRING"] = connection_string

def list_table_items(table_name: str):
    """List all items in the table."""
    try:
        table_client = get_table_client(table_name)
        items = list(table_client.list_entities())
        return items
    except Exception as e:
        raise Exception(f"Failed to list table items: {str(e)}")
