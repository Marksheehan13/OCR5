"""Shared visual system for OCR5 Streamlit surfaces."""

from __future__ import annotations

import streamlit as st


def apply_theme() -> None:
    """Apply the shared OCR5 visual language to a Streamlit page."""
    st.markdown(
        """
        <style>
        :root {
            --ocr5-radius: 16px;
            --ocr5-radius-lg: 22px;
        }

        [data-testid="stSidebar"] { display: none; }
        .block-container {
            max-width: 1180px;
            padding-top: 2.75rem;
            padding-bottom: 5rem;
        }

        h1, h2, h3 {
            letter-spacing: -0.035em;
            font-weight: 750 !important;
        }

        [data-testid="stMetric"] {
            border: 1px solid rgba(128,128,128,.18);
            border-radius: var(--ocr5-radius);
            padding: 1.1rem 1.15rem;
            background: rgba(128,128,128,.035);
        }

        [data-testid="stMetricLabel"] {
            font-size: .76rem;
            font-weight: 700;
            letter-spacing: .08em;
            text-transform: uppercase;
            opacity: .58;
        }

        [data-testid="stMetricValue"] {
            letter-spacing: -.035em;
        }

        div[data-testid="stButton"] > button,
        div[data-testid="stDownloadButton"] > button {
            min-height: 46px;
            border-radius: 14px;
            font-weight: 650;
            transition: transform .12s ease, box-shadow .12s ease;
        }

        div[data-testid="stButton"] > button:hover,
        div[data-testid="stDownloadButton"] > button:hover {
            transform: translateY(-1px);
        }

        div[data-testid="stTextInput"] input,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
            border-radius: 13px;
        }

        [data-testid="stExpander"] {
            border-radius: var(--ocr5-radius);
            border-color: rgba(128,128,128,.18);
        }

        [data-testid="stDataFrame"] {
            border-radius: var(--ocr5-radius);
            overflow: hidden;
        }

        .ocr5-page-kicker {
            font-size: .76rem;
            font-weight: 750;
            letter-spacing: .14em;
            text-transform: uppercase;
            opacity: .5;
            margin-bottom: .35rem;
        }

        .ocr5-page-title {
            font-size: 2.55rem;
            line-height: 1.05;
            font-weight: 780;
            letter-spacing: -.045em;
            margin: 0 0 .55rem;
        }

        .ocr5-page-subtitle {
            font-size: 1rem;
            opacity: .58;
            margin: 0 0 1.7rem;
            max-width: 680px;
        }

        .ocr5-section-label {
            font-size: .73rem;
            font-weight: 750;
            letter-spacing: .12em;
            text-transform: uppercase;
            opacity: .48;
            margin: 1.8rem 0 .75rem;
        }

        .ocr5-panel {
            border: 1px solid rgba(128,128,128,.18);
            border-radius: var(--ocr5-radius-lg);
            padding: 1.25rem;
            background: rgba(128,128,128,.025);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(kicker: str, title: str, subtitle: str) -> None:
    """Render a consistent OCR5 page header."""
    st.markdown(
        f'<div class="ocr5-page-kicker">{kicker}</div>'
        f'<div class="ocr5-page-title">{title}</div>'
        f'<div class="ocr5-page-subtitle">{subtitle}</div>',
        unsafe_allow_html=True,
    )
