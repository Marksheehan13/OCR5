"""OCR5 Streamlit front end.

First run: enter credentials once and click Save settings.
Later runs: OCR5 loads local settings from .env automatically.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st

from src.database import DatabaseError, get_all_invoices, initialise_database
from src.database_integration import store_invoice_result
from src.duplicate_detector import DuplicateMatch, find_duplicate_matches
from src.excel_writer import write_invoices_to_excel
from src.llm_extractor import DEFAULT_PROVIDER, PROVIDERS, ExtractionError, extract_invoice
from src.models import InvoiceExtraction
from src.settings import get_setting, save_settings

initialise_database()

st.set_page_config(page_title="OCR5 - LLM Invoice Extractor", page_icon="🧠", layout="wide")
st.title("🧠 OCR5: LLM-Based Invoice Extraction")
st.caption("Upload invoice photos or receipts. OCR5 extracts the date, supplier and total amount, verifies the result, checks for duplicates, lets you review it, and exports approved invoices to Excel.")


def _secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "") or "")
    except Exception:
        return ""


saved_provider = get_setting("OCR5_PROVIDER", DEFAULT_PROVIDER)
if saved_provider not in PROVIDERS:
    saved_provider = DEFAULT_PROVIDER

with st.sidebar:
    st.subheader("OCR5 Settings")
    provider_names = list(PROVIDERS.keys())
    provider = st.selectbox(
        "AI provider",
        options=provider_names,
        index=provider_names.index(saved_provider),
        help="Your selected provider is remembered locally after you save settings.",
    )

    env_var_name = PROVIDERS[provider]["env_var"]
    saved_api_key = get_setting("OCR5_API_KEY")
    if not saved_api_key:
        saved_api_key = _secret(env_var_name) or get_setting(env_var_name)

    api_key_input = st.text_input(
        "AI API key", value=saved_api_key, type="password",
        help="Stored locally in .env when you click Save settings. The real .env file is ignored by Git.",
    )

    st.subheader("Invoice History")
    saved_supabase_url = get_setting("SUPABASE_URL") or _secret("SUPABASE_URL")
    saved_supabase_key = get_setting("SUPABASE_KEY") or _secret("SUPABASE_KEY")
    supabase_url = st.text_input("Supabase URL", value=saved_supabase_url, placeholder="https://xxxxx.supabase.co")
    supabase_key = st.text_input("Supabase key", value=saved_supabase_key, type="password")

    if st.button("💾 Save settings", use_container_width=True, type="primary"):
        if not api_key_input:
            st.error("Enter an AI API key before saving.")
        else:
            save_settings(provider=provider, api_key=api_key_input, supabase_url=supabase_url, supabase_key=supabase_key)
            st.success("Settings saved. You won't need to enter them again on this computer.")
            st.rerun()

    if api_key_input:
        st.success("AI API key ready")
    else:
        st.warning("Add your AI API key to process invoices.")

    if supabase_url and supabase_key:
        os.environ["SUPABASE_URL"] = supabase_url
        os.environ["SUPABASE_KEY"] = supabase_key
        st.success("Supabase connected")
        database_configured = True
    else:
        database_configured = False
        st.info("Supabase is optional. Without it, extraction still works but invoice history is not saved.")

    st.caption("Your local credentials are stored in `.env`, which is excluded from Git by `.gitignore`.")

active_key = api_key_input

if "results" not in st.session_state:
    st.session_state.results = []
if "overrides" not in st.session_state:
    st.session_state.overrides = {}
if "saved_indexes" not in st.session_state:
    st.session_state.saved_indexes = set()
if "source_images" not in st.session_state:
    st.session_state.source_images = {}
if "duplicate_confirmations" not in st.session_state:
    st.session_state.duplicate_confirmations = set()
if "invoice_history_snapshot" not in st.session_state:
    st.session_state.invoice_history_snapshot = []

uploaded_files = st.file_uploader(
    "Upload invoice photos",
    type=["jpg", "jpeg", "png", "heic", "heif", "bmp", "tiff", "webp"],
    accept_multiple_files=True,
)

process_clicked = st.button("Process invoices", type="primary", disabled=not uploaded_files or not active_key)

if process_clicked and uploaded_files:
    st.session_state.results = []
    st.session_state.overrides = {}
    st.session_state.saved_indexes = set()
    st.session_state.source_images = {}
    st.session_state.duplicate_confirmations = set()

    if database_configured:
        try:
            st.session_state.invoice_history_snapshot = get_all_invoices()
        except DatabaseError:
            st.session_state.invoice_history_snapshot = []
    else:
        st.session_state.invoice_history_snapshot = []

    results: list[InvoiceExtraction] = []
    progress_area = st.container()

    for uploaded_file in uploaded_files:
        with progress_area:
            status = st.status(f"Processing {uploaded_file.name}...", expanded=True)
            status.write(f"Sending image to {provider}...")
            image_bytes = uploaded_file.getvalue()

            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp:
                tmp.write(image_bytes)
                tmp_path = tmp.name

            try:
                result = extract_invoice(tmp_path, api_key=active_key, provider=provider)
                result.source_file = uploaded_file.name
                status.write("Extraction and verification complete. Review the result before saving.")
            except ExtractionError as exc:
                status.update(label=f"Failed: {uploaded_file.name}", state="error")
                status.write(f"Error: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001
                status.update(label=f"Failed: {uploaded_file.name}", state="error")
                status.write(f"Unexpected error: {exc}")
                continue

            result_index = len(results)
            results.append(result)
            st.session_state.source_images[result_index] = {
                "bytes": image_bytes,
                "mime_type": uploaded_file.type or "application/octet-stream",
            }
            label = "Needs review" if result.needs_review else "Ready for review"
            status.update(label=f"{label}: {uploaded_file.name}", state="complete")

    st.session_state.results = results


def _build_edited_invoice(idx: int, result: InvoiceExtraction) -> InvoiceExtraction:
    overrides = st.session_state.overrides.get(f"override_{idx}", {})
    return InvoiceExtraction(
        source_file=result.source_file,
        date=type(result.date)(value=overrides.get("date", result.date.value or ""), confidence=result.date.effective_confidence, reasons=result.date.reasons),
        supplier=type(result.supplier)(value=overrides.get("supplier", result.supplier.value or ""), confidence=result.supplier.effective_confidence, reasons=result.supplier.reasons),
        amount=type(result.amount)(value=overrides.get("amount", result.amount.value or ""), confidence=result.amount.effective_confidence, reasons=result.amount.reasons),
        currency=result.currency,
        warnings=result.warnings,
        raw_text=result.raw_text,
        validation_warnings=result.validation_warnings,
    )


def _get_duplicate_matches(idx: int, invoice: InvoiceExtraction) -> list[DuplicateMatch]:
    if not database_configured:
        return []
    return find_duplicate_matches(
        invoice.supplier.value,
        invoice.date.value,
        invoice.amount.value,
        invoice.currency,
        st.session_state.invoice_history_snapshot,
    )


if st.session_state.results:
    st.divider()
    st.subheader("Results")

    for idx, result in enumerate(st.session_state.results):
        override_key = f"override_{idx}"
        overrides = st.session_state.overrides.setdefault(override_key, {})

        with st.container(border=True):
            header_cols = st.columns([3, 1])
            header_cols[0].markdown(f"**{result.source_file}**")
            if idx in st.session_state.saved_indexes:
                header_cols[1].markdown("🟢 **Saved**")
            else:
                badge = "🟡 Needs review" if result.needs_review else "🟢 Ready for review"
                header_cols[1].markdown(badge)

            cols = st.columns(3)
            fields = [("Supplier", "supplier", result.supplier), ("Date", "date", result.date), ("Amount", "amount", result.amount)]
            for col, (label, key, field_result) in zip(cols, fields):
                with col:
                    current_value = overrides.get(key, field_result.value or "")
                    new_value = st.text_input(label, value=current_value, key=f"{key}_{idx}")
                    overrides[key] = new_value
                    st.write(f"Confidence: {field_result.effective_confidence}%")

            edited_for_duplicate_check = _build_edited_invoice(idx, result)
            duplicate_matches = _get_duplicate_matches(idx, edited_for_duplicate_check)
            if duplicate_matches:
                best = duplicate_matches[0]
                st.warning(
                    f"⚠️ Possible duplicate: invoice #{best.invoice_id} already stored with "
                    f"{best.supplier} · {best.invoice_date} · {best.currency} {best.amount:.2f}."
                )
                st.caption("Matched on supplier, date, amount and currency. OCR5 will not reject it automatically.")
                confirmed = st.checkbox(
                    "I confirm this is not a duplicate and want to approve it",
                    value=idx in st.session_state.duplicate_confirmations,
                    key=f"duplicate_confirm_{idx}",
                    disabled=idx in st.session_state.saved_indexes,
                )
                if confirmed:
                    st.session_state.duplicate_confirmations.add(idx)
                else:
                    st.session_state.duplicate_confirmations.discard(idx)

            overrides["approved"] = st.checkbox(
                "Approved for export", value=not result.needs_review,
                key=f"approve_{idx}", disabled=idx in st.session_state.saved_indexes,
            )

    if database_configured:
        st.subheader("Save approved invoices")
        st.caption("Invoices are not written to Supabase until you explicitly approve and save them.")
        unsaved_approved = []
        blocked_duplicates = []
        for idx, result in enumerate(st.session_state.results):
            if idx in st.session_state.saved_indexes:
                continue
            if not st.session_state.overrides.get(f"override_{idx}", {}).get("approved", not result.needs_review):
                continue
            edited = _build_edited_invoice(idx, result)
            duplicate_matches = _get_duplicate_matches(idx, edited)
            if duplicate_matches and idx not in st.session_state.duplicate_confirmations:
                blocked_duplicates.append(idx)
                continue
            unsaved_approved.append(idx)

        if blocked_duplicates:
            names = ", ".join(st.session_state.results[idx].source_file for idx in blocked_duplicates)
            st.info(f"Possible duplicates require confirmation before saving: {names}")

        if st.button(f"💾 Save {len(unsaved_approved)} approved invoice(s) to history", type="primary", disabled=not unsaved_approved):
            save_errors = []
            for idx in unsaved_approved:
                edited = _build_edited_invoice(idx, st.session_state.results[idx])
                source = st.session_state.source_images.get(idx, {})
                try:
                    store_invoice_result(
                        edited,
                        image_bytes=source.get("bytes"),
                        mime_type=source.get("mime_type", "application/octet-stream"),
                    )
                    st.session_state.saved_indexes.add(idx)
                except DatabaseError as exc:
                    save_errors.append(f"{edited.source_file}: {exc}")

            if save_errors:
                st.error("Some invoices could not be saved:\n" + "\n".join(save_errors))
            else:
                st.success(f"Saved {len(unsaved_approved)} approved invoice(s) to invoice history, including their source images.")
            st.rerun()
    else:
        st.info("Connect Supabase to save approved invoices to invoice history. Extraction and Excel export still work without it.")

if st.session_state.results:
    st.divider()
    export_rows = []
    for idx, result in enumerate(st.session_state.results):
        overrides = st.session_state.overrides.get(f"override_{idx}", {})
        if overrides.get("approved", not result.needs_review):
            export_rows.append(_build_edited_invoice(idx, result))

    st.caption(f"{len(export_rows)} invoice(s) ready for export.")
    preview_df = pd.DataFrame([
        {"Date": r.date.value, "Supplier": r.supplier.value, "Amount": r.amount.value, "Confidence": r.overall_confidence}
        for r in export_rows
    ])
    if not preview_df.empty:
        st.dataframe(preview_df, use_container_width=True)

    if export_rows and st.button("Export approved invoices to Excel"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_out:
            write_invoices_to_excel(export_rows, tmp_out.name)
            with open(tmp_out.name, "rb") as f:
                st.download_button("Download invoices.xlsx", data=f.read(), file_name="invoices.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
