"""
app.py

Streamlit web front end for OCR5. Same UX shape as OCR4's app.py
(upload -> review -> edit -> export), but extraction is now a single
Claude API call per invoice instead of local multi-pass OCR.

Requires an Anthropic API key: add it to Streamlit Cloud's app secrets
as ANTHROPIC_API_KEY (Settings -> Secrets in the Streamlit Cloud
dashboard), or it'll prompt for one to enter directly in the sidebar
for local testing.

Run locally:
    export ANTHROPIC_API_KEY=sk-ant-...
    streamlit run app.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st

from src.excel_writer import write_invoices_to_excel
from src.llm_extractor import ExtractionError, extract_invoice
from src.models import InvoiceExtraction

st.set_page_config(page_title="OCR5 - LLM Invoice Extractor", page_icon="\U0001f9e0", layout="wide")

st.title("\U0001f9e0 OCR5: LLM-Based Invoice Extraction")
st.caption(
    "Upload photographed invoices or receipts. Claude reads each one directly and extracts "
    "date, supplier, and total amount, with its own confidence and reasoning per field."
)

with st.expander("How this differs from OCR4", expanded=False):
    st.markdown(
        """
**OCR4** ran 16 local Tesseract OCR passes per invoice, then scored candidate values with
hand-written rules (keyword proximity, letter case, position on the page). It's fully offline
and free, but it's pattern-matching, not understanding -- it can be fooled by anything the
rules didn't anticipate (e.g. mistaking a cashier's name for the store name).

**OCR5** sends the image directly to Claude and asks it to read and extract the fields. This
is slower to iterate on (no local heuristics to tweak) but categorically more capable: it
understands context the way a person reading the receipt would, rather than counting capital
letters. The tradeoff is a small per-invoice API cost and a required API key, instead of
running fully offline.
        """
    )

with st.sidebar:
    st.subheader("API Key")
    default_key = st.secrets.get("ANTHROPIC_API_KEY", "") if hasattr(st, "secrets") else ""
    api_key_input = st.text_input(
        "Anthropic API key",
        value="",
        type="password",
        placeholder="sk-ant-..." if not default_key else "Using key from Streamlit secrets",
        help="Only needed here if not already set in this app's Streamlit Cloud secrets.",
    )
    active_key = api_key_input or default_key
    if active_key:
        st.success("API key set.")
    else:
        st.warning("No API key set yet -- add one above or in app secrets to process invoices.")

if "results" not in st.session_state:
    st.session_state.results = []
if "overrides" not in st.session_state:
    st.session_state.overrides = {}

uploaded_files = st.file_uploader(
    "Upload invoice photos",
    type=["jpg", "jpeg", "png", "heic", "heif", "bmp", "tiff", "webp"],
    accept_multiple_files=True,
)

process_clicked = st.button(
    "Process invoices", type="primary", disabled=not uploaded_files or not active_key
)

if process_clicked and uploaded_files:
    st.session_state.results = []
    st.session_state.overrides = {}

    progress_area = st.container()
    results: list[InvoiceExtraction] = []

    for uploaded_file in uploaded_files:
        with progress_area:
            status = st.status(f"Processing {uploaded_file.name}...", expanded=True)
            status.write("Sending image to Claude...")

            with tempfile.NamedTemporaryFile(
                delete=False, suffix=Path(uploaded_file.name).suffix
            ) as tmp:
                tmp.write(uploaded_file.getbuffer())
                tmp_path = tmp.name

            try:
                result = extract_invoice(tmp_path, api_key=active_key)
            except ExtractionError as exc:
                status.update(label=f"Failed: {uploaded_file.name}", state="error")
                status.write(f"Error: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 - surface any unexpected failure to the user
                status.update(label=f"Failed: {uploaded_file.name}", state="error")
                status.write(f"Unexpected error: {exc}")
                continue

            status.write("Parsing response...")
            result.source_file = uploaded_file.name
            results.append(result)

            label = "Needs review" if result.needs_review else "Done"
            status.update(label=f"{label}: {uploaded_file.name}", state="complete")

    st.session_state.results = results

# --- Results display (identical UX to OCR4's app.py) --------------------------

if st.session_state.results:
    st.divider()
    st.subheader("Results")

    for idx, result in enumerate(st.session_state.results):
        override_key = f"override_{idx}"
        overrides = st.session_state.overrides.setdefault(override_key, {})

        with st.container(border=True):
            header_cols = st.columns([3, 1])
            header_cols[0].markdown(f"**{result.source_file}**")
            badge = "\U0001f7e2 High confidence" if not result.needs_review else "\U0001f7e1 Needs review"
            header_cols[1].markdown(badge)

            if result.warnings:
                for w in result.warnings:
                    st.warning(w)

            cols = st.columns(3)
            field_specs = [
                ("Supplier", "supplier", result.supplier),
                ("Date", "date", result.date),
                ("Amount", "amount", result.amount),
            ]
            for col, (label, key, field_result) in zip(cols, field_specs):
                with col:
                    st.markdown(f"**{label}**")
                    current_value = overrides.get(key, field_result.value or "")
                    new_value = st.text_input(
                        f"{label}_{idx}",
                        value=current_value,
                        label_visibility="collapsed",
                        key=f"input_{key}_{idx}",
                    )
                    overrides[key] = new_value
                    conf_color = (
                        "green"
                        if field_result.confidence >= 90
                        else "orange"
                        if field_result.confidence >= 70
                        else "red"
                    )
                    st.markdown(f":{conf_color}[Confidence: {field_result.confidence}%]")
                    with st.popover("Why?"):
                        for reason in field_result.reasons:
                            st.write(f"- {reason}")

            approved = st.checkbox("Approved for export", value=not result.needs_review, key=f"approve_{idx}")
            overrides["approved"] = approved

    st.divider()

    export_rows = []
    for idx, result in enumerate(st.session_state.results):
        overrides = st.session_state.overrides.get(f"override_{idx}", {})
        if not overrides.get("approved", True):
            continue
        edited = InvoiceExtraction(
            source_file=result.source_file,
            date=type(result.date)(
                value=overrides.get("date") or None,
                confidence=result.date.confidence,
                reasons=result.date.reasons,
            ),
            supplier=type(result.supplier)(
                value=overrides.get("supplier") or None,
                confidence=result.supplier.confidence,
                reasons=result.supplier.reasons,
            ),
            amount=type(result.amount)(
                value=overrides.get("amount") or None,
                confidence=result.amount.confidence,
                reasons=result.amount.reasons,
            ),
            currency=result.currency,
            warnings=result.warnings,
            raw_text=result.raw_text,
        )
        export_rows.append(edited)

    st.caption(f"{len(export_rows)} of {len(st.session_state.results)} invoice(s) approved for export.")

    preview_df = pd.DataFrame(
        [
            {
                "Invoice Date": r.date.value,
                "Supplier": r.supplier.value,
                "Amount": r.amount.value,
                "Confidence": r.overall_confidence,
                "Review Required": "Yes" if r.needs_review else "No",
            }
            for r in export_rows
        ]
    )
    if not preview_df.empty:
        st.dataframe(preview_df, use_container_width=True)

    if export_rows and st.button("Export approved invoices to Excel"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_out:
            write_invoices_to_excel(export_rows, tmp_out.name)
            with open(tmp_out.name, "rb") as f:
                st.download_button(
                    "Download invoices.xlsx",
                    data=f.read(),
                    file_name="invoices.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
