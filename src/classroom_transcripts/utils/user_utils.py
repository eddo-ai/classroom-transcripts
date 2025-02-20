from enum import Enum
from typing import Optional
import streamlit as st
import os


class UserRole(Enum):
    ADMIN = "admin"
    COACH = "coach"
    USER = "user"  # Default role for authenticated users


def get_user_roles(user_id: str) -> list[str]:
    """Get list of role names from user roles response"""
    try:
        # For now return empty list since role API is not implemented
        # TODO: Implement actual role API integration
        return []
    except Exception as e:
        st.error(f"Error getting user roles: {str(e)}")
        return []


def get_user_role(user) -> Optional[UserRole]:
    """Get user role with USER as default for authenticated users"""
    if not user or not hasattr(user, "email"):
        return None

    try:
        # Get roles from API response
        roles = get_user_roles(getattr(user, "user_id", None))

        # Check for admin/coach roles
        if "admin" in roles:
            return UserRole.ADMIN
        if "coach" in roles:
            return UserRole.COACH

        return UserRole.USER
    except (ValueError, AttributeError):
        return UserRole.USER


def validate_user_permissions():
    """Validate user is logged in and has valid email"""
    if not st.experimental_user.get("is_logged_in"):
         st.login()

    user = st.experimental_user
    if not user or not getattr(user, "email", None):
        st.error("User authentication failed - no valid email")
        st.stop()

    # Add email validation check
    if not getattr(user, "email_verified", False):
        st.error("Please verify your email address before accessing transcripts")
        st.stop()

    role = get_user_role(user)
    if role is None:
        st.error("User authentication failed - unable to determine role")
        st.stop()

    return user, role


def is_admin_or_coach(role: Optional[UserRole]) -> bool:
    """Check if user has admin/coach permissions"""
    if role is None:
        return False
    return role in (UserRole.ADMIN, UserRole.COACH)
