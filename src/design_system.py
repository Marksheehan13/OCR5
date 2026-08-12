"""Reusable OCR5 Streamlit design system primitives."""
from __future__ import annotations

import html
import streamlit as st


def inject_styles() -> None:
    st.markdown("""
    <style>
    :root { --ocr5-radius: 16px; }
    .block-container { max-width: 1180px; padding-top: 2.75rem; padding-bottom: 5rem; }
    .ocr5-page-kicker { font-size:.72rem; font-weight:800; letter-spacing:.13em; text-transform:uppercase; opacity:.48; }
    .ocr5-page-title { font-size:2.35rem; line-height:1.05; font-weight:760; letter-spacing:-.045em; margin:.25rem 0 .35rem; }
    .ocr5-page-subtitle { opacity:.58; margin:0 0 1.5rem; }
    .ocr5-section { font-size:.72rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase; opacity:.48; margin:1.75rem 0 .7rem; }
    .ocr5-card { padding:1rem 1.15rem; border:1px solid rgba(128,128,128,.20); border-radius:var(--ocr5-radius); background:rgba(128,128,128,.035); }
    .ocr5-card-title { font-weight:720; font-size:1rem; }
    .ocr5-card-meta { margin-top:.25rem; font-size:.82rem; opacity:.56; }
    .ocr5-metric { padding:1rem 1.1rem; border:1px solid rgba(128,128,128,.18); border-radius:var(--ocr5-radius); }
    .ocr5-metric-label { font-size:.75rem; opacity:.55; }
    .ocr5-metric-value { font-size:1.55rem; font-weight:760; letter-spacing:-.025em; margin-top:.2rem; }
    .ocr5-empty { text-align:center; padding:3rem 1rem; border:1px dashed rgba(128,128,128,.25); border-radius:var(--ocr5-radius); opacity:.58; }
    div[data-testid="stButton"] button { border-radius:14px; min-height:46px; font-weight:650; }
    </style>
    """, unsafe_allow_html=True)


def page_header(kicker: str, title: str, subtitle: str = "") -> None:
    st.markdown(
        f'<div class="ocr5-page-kicker">{html.escape(kicker)}</div>'
        f'<div class="ocr5-page-title">{html.escape(title)}</div>'
        + (f'<div class="ocr5-page-subtitle">{html.escape(subtitle)}</div>' if subtitle else ""),
        unsafe_allow_html=True,
    )


def section_label(label: str) -> None:
    st.markdown(f'<div class="ocr5-section">{html.escape(label)}</div>', unsafe_allow_html=True)


def metric_card(label: str, value: str) -> None:
    st.markdown(f'<div class="ocr5-metric"><div class="ocr5-metric-label">{html.escape(label)}</div><div class="ocr5-metric-value">{html.escape(value)}</div></div>', unsafe_allow_html=True)


def empty_state(title: str, description: str = "") -> None:
    body = f'<strong>{html.escape(title)}</strong>'
    if description:
        body += f'<br><span>{html.escape(description)}</span>'
    st.markdown(f'<div class="ocr5-empty">{body}</div>', unsafe_allow_html=True)
