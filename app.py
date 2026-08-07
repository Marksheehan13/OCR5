"""
app.py

Streamlit web front end for OCR5.

Flow:
Upload invoice
        ↓
Claude Vision extraction
        ↓
Review/edit results
        ↓
Save invoice permanently to SQLite memory database
        ↓
Export to Excel

Requires an Anthropic API key.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st

from src.database import initialise_database
from src.database_integration import store_invoice_result
from src.excel_writer import write_invoices_to_excel
from src.llm_extractor import ExtractionError, extract_invoice
from src.models import InvoiceExtraction


# Create database if it does not exist
initialise_database()


st.set_page_config(
    page_title="OCR5 - LLM Invoice Extractor",
    page_icon="🧠",
    layout="wide",
)


st.title("🧠 OCR5: LLM-Based Invoice Extraction")

st.caption(
    "Upload photographed invoices or receipts. Claude extracts "
    "date, supplier and total amount, then OCR5 remembers processed invoices."
)


# ---------------- SIDEBAR ----------------

with st.sidebar:
    st.subheader("API Key")

    default_key = (
        st.secrets.get("ANTHROPIC_API_KEY", "")
        if hasattr(st, "secrets")
        else ""
    )

    api_key_input = st.text_input(
        "Anthropic API key",
        value="",
        type="password",
        placeholder="sk-ant-..."
        if not default_key
        else "Using Streamlit secrets",
    )

    active_key = api_key_input or default_key

    if active_key:
        st.success("API key set.")
    else:
        st.warning(
            "No API key set. Add one above or in Streamlit secrets."
        )


# ---------------- SESSION STATE ----------------

if "results" not in st.session_state:
    st.session_state.results = []

if "overrides" not in st.session_state:
    st.session_state.overrides = {}


# ---------------- UPLOAD ----------------

uploaded_files = st.file_uploader(
    "Upload invoice photos",
    type=[
        "jpg",
        "jpeg",
        "png",
        "heic",
        "heif",
        "bmp",
        "tiff",
        "webp",
    ],
    accept_multiple_files=True,
)


process_clicked = st.button(
    "Process invoices",
    type="primary",
    disabled=not uploaded_files or not active_key,
)


# ---------------- PROCESSING ----------------

if process_clicked and uploaded_files:

    st.session_state.results = []
    st.session_state.overrides = {}

    results: list[InvoiceExtraction] = []

    progress_area = st.container()


    for uploaded_file in uploaded_files:

        with progress_area:

            status = st.status(
                f"Processing {uploaded_file.name}...",
                expanded=True,
            )

            status.write(
                "Sending image to Claude..."
            )


            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=Path(uploaded_file.name).suffix,
            ) as tmp:

                tmp.write(
                    uploaded_file.getbuffer()
                )

                tmp_path = tmp.name


            try:

                result = extract_invoice(
                    tmp_path,
                    api_key=active_key,
                )


                # Store original filename
                result.source_file = uploaded_file.name


                # Save permanently into database memory
                database_result = store_invoice_result(
                    result
                )


                status.write(
                    "Saved to OCR5 memory database."
                )


            except ExtractionError as exc:

                status.update(
                    label=f"Failed: {uploaded_file.name}",
                    state="error",
                )

                status.write(
                    f"Error: {exc}"
                )

                continue


            except Exception as exc:

                status.update(
                    label=f"Failed: {uploaded_file.name}",
                    state="error",
                )

                status.write(
                    f"Unexpected error: {exc}"
                )

                continue


            results.append(result)


            label = (
                "Needs review"
                if result.needs_review
                else "Done"
            )


            status.update(
                label=f"{label}: {uploaded_file.name}",
                state="complete",
            )


    st.session_state.results = results



# ---------------- RESULTS DISPLAY ----------------


if st.session_state.results:

    st.divider()

    st.subheader("Results")


    for idx, result in enumerate(
        st.session_state.results
    ):

        override_key = f"override_{idx}"

        overrides = (
            st.session_state.overrides
            .setdefault(
                override_key,
                {},
            )
        )


        with st.container(border=True):

            header_cols = st.columns([3, 1])

            header_cols[0].markdown(
                f"**{result.source_file}**"
            )


            badge = (
                "🟢 High confidence"
                if not result.needs_review
                else "🟡 Needs review"
            )

            header_cols[1].markdown(
                badge
            )


            cols = st.columns(3)


            fields = [
                (
                    "Supplier",
                    "supplier",
                    result.supplier,
                ),
                (
                    "Date",
                    "date",
                    result.date,
                ),
                (
                    "Amount",
                    "amount",
                    result.amount,
                ),
            ]


            for col, (
                label,
                key,
                field_result,
            ) in zip(
                cols,
                fields,
            ):

                with col:

                    st.markdown(
                        f"**{label}**"
                    )


                    current_value = (
                        overrides.get(
                            key,
                            field_result.value
                            or "",
                        )
                    )


                    new_value = st.text_input(
                        label,
                        value=current_value,
                        key=f"{key}_{idx}",
                    )


                    overrides[key] = new_value


                    st.write(
                        f"Confidence: {field_result.confidence}%"
                    )


            overrides["approved"] = st.checkbox(
                "Approved for export",
                value=not result.needs_review,
                key=f"approve_{idx}",
            )



# ---------------- EXPORT ----------------


if st.session_state.results:

    st.divider()

    export_rows = []


    for idx, result in enumerate(
        st.session_state.results
    ):

        overrides = (
            st.session_state.overrides
            .get(
                f"override_{idx}",
                {},
            )
        )


        if overrides.get(
            "approved",
            True,
        ):

            edited = InvoiceExtraction(
                source_file=result.source_file,
                date=type(result.date)(
                    value=overrides.get(
                        "date"
                    ),
                    confidence=result.date.confidence,
                    reasons=result.date.reasons,
                ),
                supplier=type(result.supplier)(
                    value=overrides.get(
                        "supplier"
                    ),
                    confidence=result.supplier.confidence,
                    reasons=result.supplier.reasons,
                ),
                amount=type(result.amount)(
                    value=overrides.get(
                        "amount"
                    ),
                    confidence=result.amount.confidence,
                    reasons=result.amount.reasons,
                ),
                currency=result.currency,
                warnings=result.warnings,
                raw_text=result.raw_text,
            )

            export_rows.append(
                edited
            )


    st.caption(
        f"{len(export_rows)} invoice(s) ready for export."
    )


    preview_df = pd.DataFrame(
        [
            {
                "Date": r.date.value,
                "Supplier": r.supplier.value,
                "Amount": r.amount.value,
                "Confidence": r.overall_confidence,
            }
            for r in export_rows
        ]
    )


    if not preview_df.empty:

        st.dataframe(
            preview_df,
            use_container_width=True,
        )


    if export_rows and st.button(
        "Export approved invoices to Excel"
    ):

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".xlsx",
        ) as tmp_out:

            write_invoices_to_excel(
                export_rows,
                tmp_out.name,
            )


            with open(
                tmp_out.name,
                "rb",
            ) as f:

                st.download_button(
                    "Download invoices.xlsx",
                    data=f.read(),
                    file_name="invoices.xlsx",
                    mime=(
                        "application/"
                        "vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                )
