"""OCR5 Streamlit development application.

This is the Streamlit preview for the working OCR5 bookkeeping workflow.
The OCR/extraction, validation, duplicate detection, persistence and Excel
export logic remains in src/; this file provides the interactive UI around it.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd
import streamlit as st

from src.client_database import archive_client, create_client, list_clients, restore_client
from src.database import DatabaseError, get_all_invoices, initialise_database
from src.database_integration import store_invoice_result
from src.duplicate_detector import DuplicateMatch, find_duplicate_matches
from src.excel_writer import write_invoices_to_excel
from src.llm_extractor import DEFAULT_PROVIDER, PROVIDERS, ExtractionError, extract_invoice
from src.models import InvoiceExtraction, LineItem
from src.settings import get_setting, save_settings

initialise_database()
st.set_page_config(page_title="OCR5 Bookkeeping", page_icon="🧾", layout="wide")


def _secret(name: str) -> str:
    try:
        return str(st.secrets.get(name, "") or "")
    except Exception:
        return ""


def _load_clients() -> list[dict]:
    try:
        return list_clients()
    except Exception:
        return []


def _reset_invoice_session() -> None:
    st.session_state.results = []
    st.session_state.overrides = {}
    st.session_state.saved_indexes = set()
    st.session_state.source_images = {}
    st.session_state.duplicate_confirmations = set()
    st.session_state.invoice_history_snapshot = []


# ---------- session state ----------
for key, default in {
    "results": [],
    "overrides": {},
    "saved_indexes": set(),
    "source_images": {},
    "duplicate_confirmations": set(),
    "invoice_history_snapshot": [],
    "active_client_id": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

clients = _load_clients()
client_ids = {int(c["id"]): c for c in clients}
if st.session_state.active_client_id not in client_ids:
    st.session_state.active_client_id = int(clients[0]["id"]) if clients else None

# ---------- sidebar ----------
with st.sidebar:
    st.markdown("# 🧾 OCR5")
    st.caption("AI-powered bookkeeping workspace")
    st.divider()

    st.subheader("Clients")
    if clients:
        options = [int(c["id"]) for c in clients]
        labels = {int(c["id"]): (c.get("company_name") or c.get("name") or f"Client {c['id']}") for c in clients}
        current_index = options.index(st.session_state.active_client_id) if st.session_state.active_client_id in options else 0
        selected = st.selectbox(
            "Active client",
            options=options,
            index=current_index,
            format_func=lambda cid: labels[cid],
            key="client_selector",
        )
        if selected != st.session_state.active_client_id:
            st.session_state.active_client_id = selected
            _reset_invoice_session()
            st.rerun()
        active_client = client_ids[selected]
        st.success(f"Working in **{labels[selected]}**")
    else:
        active_client = None
        st.warning("Create your first client to start saving invoices.")

    with st.expander("+ Add client", expanded=not clients):
        client_name = st.text_input("Client name *", placeholder="John Murphy Ltd", key="new_client_name")
        company_name = st.text_input("Company name", placeholder="Optional", key="new_client_company")
        client_email = st.text_input("Email", key="new_client_email")
        client_phone = st.text_input("Phone", key="new_client_phone")
        client_address = st.text_area("Address", key="new_client_address")
        if st.button("Create client", type="primary", use_container_width=True):
            if not client_name.strip():
                st.error("Client name is required.")
            else:
                try:
                    created = create_client(client_name, company_name, client_email, client_phone, client_address)
                    st.session_state.active_client_id = int(created["id"])
                    _reset_invoice_session()
                    st.success("Client created.")
                    st.rerun()
                except DatabaseError as exc:
                    st.error(str(exc))

    if clients:
        with st.expander("Manage clients"):
            for client in clients:
                cid = int(client["id"])
                title = client.get("company_name") or client.get("name") or f"Client {cid}"
                st.markdown(f"**{title}**")
                st.caption(client.get("email") or client.get("phone") or "No contact details")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Archive", key=f"archive_{cid}", disabled=cid == st.session_state.active_client_id):
                        try:
                            archive_client(cid)
                            st.rerun()
                        except DatabaseError as exc:
                            st.error(str(exc))
            archived = []
            try:
                archived = [c for c in list_clients(include_inactive=True) if not c.get("active", True)]
            except Exception:
                pass
            if archived:
                st.caption("Archived")
                for client in archived:
                    cid = int(client["id"])
                    title = client.get("company_name") or client.get("name") or f"Client {cid}"
                    if st.button(f"Restore {title}", key=f"restore_{cid}"):
                        try:
                            restore_client(cid)
                            st.rerun()
                        except DatabaseError as exc:
                            st.error(str(exc))

    st.divider()
    st.subheader("AI Settings")
    saved_provider = get_setting("OCR5_PROVIDER", DEFAULT_PROVIDER)
    if saved_provider not in PROVIDERS:
        saved_provider = DEFAULT_PROVIDER
    provider_names = list(PROVIDERS.keys())
    provider = st.selectbox("AI provider", provider_names, index=provider_names.index(saved_provider))
    env_var_name = PROVIDERS[provider]["env_var"]
    saved_api_key = get_setting("OCR5_API_KEY") or _secret(env_var_name) or get_setting(env_var_name)
    api_key_input = st.text_input("AI API key", value=saved_api_key, type="password")

    st.subheader("Supabase")
    saved_supabase_url = get_setting("SUPABASE_URL") or _secret("SUPABASE_URL")
    saved_supabase_key = get_setting("SUPABASE_KEY") or _secret("SUPABASE_KEY")
    supabase_url = st.text_input("Supabase URL", value=saved_supabase_url, placeholder="https://xxxxx.supabase.co")
    supabase_key = st.text_input("Supabase key", value=saved_supabase_key, type="password")
    if st.button("Save settings", use_container_width=True):
        if not api_key_input:
            st.error("Enter an AI API key before saving.")
        else:
            save_settings(provider=provider, api_key=api_key_input, supabase_url=supabase_url, supabase_key=supabase_key)
            st.success("Settings saved.")
            st.rerun()

    database_configured = bool(supabase_url and supabase_key)
    if database_configured:
        os.environ["SUPABASE_URL"] = supabase_url
        os.environ["SUPABASE_KEY"] = supabase_key
        st.success("Supabase connected")
    else:
        st.info("Connect Supabase to persist bookkeeping data.")

# ---------- main workspace ----------
if active_client:
    client_title = active_client.get("company_name") or active_client.get("name") or "Active client"
    st.title(client_title)
    st.caption("Private bookkeeping workspace · every saved invoice is attached to this client.")
else:
    st.title("OCR5 Bookkeeping")
    st.info("Create a client in the sidebar before processing invoices.")

active_key = api_key_input
active_client_id = st.session_state.active_client_id

if not active_client:
    st.stop()

# ---------- upload / extraction ----------
st.subheader("Scan invoices")
st.caption(f"Invoices processed here will be stored privately under **{client_title}**.")
uploaded_files = st.file_uploader(
    "Upload invoice photos or receipts",
    type=["jpg", "jpeg", "png", "heic", "heif", "bmp", "tiff", "webp"],
    accept_multiple_files=True,
)
process_clicked = st.button("Process invoices", type="primary", disabled=not uploaded_files or not active_key)

if process_clicked and uploaded_files:
    _reset_invoice_session()
    if database_configured:
        try:
            st.session_state.invoice_history_snapshot = get_all_invoices(active_client_id)
        except DatabaseError:
            st.session_state.invoice_history_snapshot = []

    results: list[InvoiceExtraction] = []
    for uploaded_file in uploaded_files:
        status = st.status(f"Processing {uploaded_file.name}...", expanded=True)
        status.write(f"Sending image to {provider}...")
        image_bytes = uploaded_file.getvalue()
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        try:
            result = extract_invoice(tmp_path, api_key=active_key, provider=provider)
            result.source_file = uploaded_file.name
            status.write("Extraction and verification complete.")
        except ExtractionError as exc:
            status.update(label=f"Failed: {uploaded_file.name}", state="error")
            status.write(str(exc))
            continue
        except Exception as exc:
            status.update(label=f"Failed: {uploaded_file.name}", state="error")
            status.write(f"Unexpected error: {exc}")
            continue
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        idx = len(results)
        results.append(result)
        st.session_state.source_images[idx] = {"bytes": image_bytes, "mime_type": uploaded_file.type or "application/octet-stream"}
        status.update(label=f"{'Needs review' if result.needs_review else 'Ready'}: {uploaded_file.name}", state="complete")
    st.session_state.results = results


def _build_edited_invoice(idx: int, result: InvoiceExtraction) -> InvoiceExtraction:
    overrides = st.session_state.overrides.get(f"override_{idx}", {})
    field = type(result.date)
    line_items = []
    for item_idx, item in enumerate(result.line_items):
        edited = overrides.get("line_items", {}).get(item_idx, {})
        line_items.append(LineItem(
            description=edited.get("description", item.description), quantity=edited.get("quantity", item.quantity),
            unit_price=edited.get("unit_price", item.unit_price), vat_rate=edited.get("vat_rate", item.vat_rate),
            line_total=edited.get("line_total", item.line_total), confidence=item.confidence, warnings=item.warnings,
        ))
    return InvoiceExtraction(
        source_file=result.source_file,
        date=field(value=overrides.get("date", result.date.value or ""), confidence=result.date.effective_confidence, reasons=result.date.reasons),
        supplier=field(value=overrides.get("supplier", result.supplier.value or ""), confidence=result.supplier.effective_confidence, reasons=result.supplier.reasons),
        amount=field(value=overrides.get("amount", result.amount.value or ""), confidence=result.amount.effective_confidence, reasons=result.amount.reasons),
        currency=overrides.get("currency", result.currency),
        invoice_number=field(value=overrides.get("invoice_number", result.invoice_number.value or ""), confidence=result.invoice_number.effective_confidence, reasons=result.invoice_number.reasons),
        subtotal=field(value=overrides.get("subtotal", result.subtotal.value or ""), confidence=result.subtotal.effective_confidence, reasons=result.subtotal.reasons),
        vat_amount=field(value=overrides.get("vat_amount", result.vat_amount.value or ""), confidence=result.vat_amount.effective_confidence, reasons=result.vat_amount.reasons),
        vat_rate=field(value=overrides.get("vat_rate", result.vat_rate.value or ""), confidence=result.vat_rate.effective_confidence, reasons=result.vat_rate.reasons),
        line_items=line_items, warnings=result.warnings, raw_text=result.raw_text, validation_warnings=result.validation_warnings,
    )


def _get_duplicate_matches(invoice: InvoiceExtraction) -> list[DuplicateMatch]:
    if not database_configured:
        return []
    return find_duplicate_matches(invoice.supplier.value, invoice.date.value, invoice.amount.value, invoice.currency, st.session_state.invoice_history_snapshot)


# ---------- review ----------
if st.session_state.results:
    st.divider()
    st.subheader("Review extracted invoices")
    for idx, result in enumerate(st.session_state.results):
        overrides = st.session_state.overrides.setdefault(f"override_{idx}", {})
        with st.container(border=True):
            head = st.columns([3, 1])
            head[0].markdown(f"**{result.source_file}**")
            head[1].markdown("🟢 Saved" if idx in st.session_state.saved_indexes else ("🟡 Needs review" if result.needs_review else "🟢 Ready"))

            cols = st.columns(4)
            for col, label, key, field_result in [
                (cols[0], "Supplier", "supplier", result.supplier), (cols[1], "Invoice number", "invoice_number", result.invoice_number),
                (cols[2], "Date", "date", result.date), (cols[3], "Currency", "currency", None),
            ]:
                with col:
                    value = overrides.get(key, field_result.value if field_result else result.currency) or ""
                    overrides[key] = st.text_input(label, value=value, key=f"{key}_{idx}")
                    if field_result:
                        st.caption(f"Confidence {field_result.effective_confidence}%")

            cols = st.columns(4)
            for col, label, key, field_result in [
                (cols[0], "Subtotal", "subtotal", result.subtotal), (cols[1], "VAT amount", "vat_amount", result.vat_amount),
                (cols[2], "VAT rate %", "vat_rate", result.vat_rate), (cols[3], "Final total", "amount", result.amount),
            ]:
                with col:
                    overrides[key] = st.text_input(label, value=overrides.get(key, field_result.value or ""), key=f"{key}_{idx}")
                    st.caption(f"Confidence {field_result.effective_confidence}%")

            if result.line_items:
                st.markdown("#### Line items")
                line_overrides = overrides.setdefault("line_items", {})
                for item_idx, item in enumerate(result.line_items):
                    values = line_overrides.setdefault(item_idx, {})
                    cols = st.columns(5)
                    for col, label, key, value in zip(cols, ["Description", "Quantity", "Unit price", "VAT %", "Line total"], ["description", "quantity", "unit_price", "vat_rate", "line_total"], [item.description, item.quantity or "", item.unit_price or "", item.vat_rate or "", item.line_total or ""]):
                        with col:
                            values[key] = st.text_input(label, value=values.get(key, value), key=f"line_{idx}_{item_idx}_{key}")
                    if item.warnings:
                        st.warning("; ".join(item.warnings))
            else:
                st.info("No line items were confidently identified.")

            edited = _build_edited_invoice(idx, result)
            matches = _get_duplicate_matches(edited)
            if matches:
                best = matches[0]
                st.warning(f"Possible duplicate: invoice #{best.invoice_id} · {best.supplier} · {best.invoice_date} · {best.currency} {best.amount:.2f}")
                confirmed = st.checkbox("I confirm this is not a duplicate", value=idx in st.session_state.duplicate_confirmations, key=f"duplicate_confirm_{idx}")
                if confirmed:
                    st.session_state.duplicate_confirmations.add(idx)
                else:
                    st.session_state.duplicate_confirmations.discard(idx)
            overrides["approved"] = st.checkbox("Approved for export", value=not result.needs_review, key=f"approve_{idx}", disabled=idx in st.session_state.saved_indexes)

    if database_configured:
        approved = []
        blocked = []
        for idx, result in enumerate(st.session_state.results):
            if idx in st.session_state.saved_indexes:
                continue
            if not st.session_state.overrides.get(f"override_{idx}", {}).get("approved", not result.needs_review):
                continue
            edited = _build_edited_invoice(idx, result)
            matches = _get_duplicate_matches(edited)
            if matches and idx not in st.session_state.duplicate_confirmations:
                blocked.append(idx)
            else:
                approved.append(idx)
        if blocked:
            st.info("Possible duplicates require confirmation before saving: " + ", ".join(st.session_state.results[i].source_file for i in blocked))
        if st.button(f"💾 Save {len(approved)} approved invoice(s) for {client_title}", type="primary", disabled=not approved):
            errors = []
            for idx in approved:
                edited = _build_edited_invoice(idx, st.session_state.results[idx])
                source = st.session_state.source_images.get(idx, {})
                try:
                    store_invoice_result(edited, image_bytes=source.get("bytes"), mime_type=source.get("mime_type", "application/octet-stream"), client_id=active_client_id)
                    st.session_state.saved_indexes.add(idx)
                except DatabaseError as exc:
                    errors.append(f"{edited.source_file}: {exc}")
            if errors:
                st.error("Some invoices could not be saved:\n" + "\n".join(errors))
            else:
                st.success(f"Saved {len(approved)} invoice(s) to {client_title}.")
            st.rerun()

    export_rows = []
    for idx, result in enumerate(st.session_state.results):
        if st.session_state.overrides.get(f"override_{idx}", {}).get("approved", not result.needs_review):
            export_rows.append(_build_edited_invoice(idx, result))
    if export_rows:
        st.divider()
        st.subheader("Excel export")
        preview = pd.DataFrame([{"Invoice number": r.invoice_number.value, "Date": r.date.value, "Supplier": r.supplier.value, "Total": r.amount.value, "Currency": r.currency, "Confidence": r.overall_confidence} for r in export_rows])
        st.dataframe(preview, use_container_width=True)
        if st.button("Prepare Excel export"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_out:
                write_invoices_to_excel(export_rows, tmp_out.name)
                with open(tmp_out.name, "rb") as f:
                    st.download_button("Download invoices.xlsx", data=f.read(), file_name=f"{client_title.replace(' ', '_')}_invoices.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---------- client overview ----------
st.divider()
st.subheader("Client overview")
if database_configured:
    try:
        history = get_all_invoices(active_client_id)
        total = sum(float(row[3]) for row in history if row[3] is not None)
        vat = sum(float(row[10]) for row in history if row[10] is not None)
        a, b, c = st.columns(3)
        a.metric("Invoices", len(history))
        b.metric("Total spend", f"{total:,.2f}")
        c.metric("VAT", f"{vat:,.2f}")
        if history:
            st.dataframe(pd.DataFrame([{"Invoice": r[8], "Date": r[2], "Supplier": r[1], "Amount": r[3], "Currency": r[4]} for r in history]), use_container_width=True)
    except DatabaseError as exc:
        st.warning(str(exc))
else:
    st.info("Connect Supabase to see this client's saved invoices and bookkeeping totals.")
