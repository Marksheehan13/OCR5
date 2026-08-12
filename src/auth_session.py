"""Streamlit session helpers for OCR5 authentication.

The authenticated Supabase client is kept in Streamlit session state so its
access token is used for RLS-protected database requests.
"""
from __future__ import annotations

import streamlit as st
from supabase import Client

from .auth import create_auth_client, sign_in, sign_up

AUTH_CLIENT_KEY = "ocr5_auth_client"
AUTH_USER_KEY = "ocr5_auth_user"


def get_auth_client() -> Client:
    client = st.session_state.get(AUTH_CLIENT_KEY)
    if client is None:
        client = create_auth_client()
        st.session_state[AUTH_CLIENT_KEY] = client
    return client


def current_user():
    client = st.session_state.get(AUTH_CLIENT_KEY)
    if client is None:
        return st.session_state.get(AUTH_USER_KEY)
    try:
        user = client.auth.get_user()
        if user and user.user:
            st.session_state[AUTH_USER_KEY] = user.user
            return user.user
    except Exception:
        pass
    return None


def login(email: str, password: str):
    client, response = sign_in(email, password)
    st.session_state[AUTH_CLIENT_KEY] = client
    st.session_state[AUTH_USER_KEY] = response.user
    return response


def register(email: str, password: str):
    client, response = sign_up(email, password)
    st.session_state[AUTH_CLIENT_KEY] = client
    if response.user:
        st.session_state[AUTH_USER_KEY] = response.user
    return response


def logout() -> None:
    client = st.session_state.pop(AUTH_CLIENT_KEY, None)
    st.session_state.pop(AUTH_USER_KEY, None)
    if client is not None:
        try:
            client.auth.sign_out()
        except Exception:
            pass


def is_authenticated() -> bool:
    return current_user() is not None
