"""
invoice_history.py

OCR5 memory viewer.

Displays previously processed invoices
stored in the SQLite database.
"""


import pandas as pd
import streamlit as st

from src.database import get_all_invoices


st.set_page_config(
    page_title="OCR5 Invoice History",
    page_icon="📚",
    layout="wide",
)


st.title("📚 OCR5 Invoice Memory")

st.caption(
    "Previous invoices stored in the OCR5 database."
)


# Load invoices

invoices = get_all_invoices()


if not invoices:

    st.info(
        "No invoices have been processed yet."
    )

    st.stop()



# Convert database rows into dataframe

df = pd.DataFrame(
    invoices,
    columns=[
        "ID",
        "Supplier",
        "Invoice Date",
        "Amount",
        "Currency",
        "Confidence",
        "Image",
        "Created At",
    ],
)


# ---------------- SEARCH ----------------


search = st.text_input(
    "Search supplier"
)


if search:

    df = df[
        df["Supplier"]
        .str.contains(
            search,
            case=False,
            na=False,
        )
    ]



# ---------------- DISPLAY ----------------


st.subheader(
    f"{len(df)} stored invoices"
)


st.dataframe(
    df,
    use_container_width=True,
)



# ---------------- METRICS ----------------


col1, col2, col3 = st.columns(3)


with col1:

    st.metric(
        "Total invoices",
        len(df),
    )


with col2:

    average_confidence = round(
        df["Confidence"].mean(),
        1,
    )

    st.metric(
        "Average confidence",
        f"{average_confidence}%",
    )


with col3:

    total_amount = df["Amount"].sum()

    st.metric(
        "Total processed value",
        f"{total_amount:.2f}",
    )
