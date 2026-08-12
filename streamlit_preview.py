"""Development preview: renders the standalone OCR5 website inside Streamlit.

The production UI lives in frontend/. This file is intentionally a thin bridge so
Streamlit can remain the visual development environment without duplicating the
frontend design in Streamlit widgets.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent
PORT = 8000

st.set_page_config(page_title="OCR5", page_icon="✦", layout="wide", initial_sidebar_state="collapsed")


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _start_web_server() -> None:
    if _port_open(PORT):
        return
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "start_web.py")],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    st.session_state["ocr5_web_pid"] = process.pid
    for _ in range(30):
        if _port_open(PORT):
            return
        time.sleep(0.15)


_start_web_server()

# The iframe points at the same standalone frontend used outside Streamlit.
# This means visual changes only need to be made once.
components.iframe(f"http://127.0.0.1:{PORT}", height=1000, scrolling=True)
