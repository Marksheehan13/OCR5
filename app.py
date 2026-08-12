"""OCR5 Streamlit application.

Primary workflow:
    Clients -> Client -> Financial year -> Bookkeeping workspace.

The OCR, validation, duplicate detection, persistence and export logic remains
in src/. This file is intentionally a thin application shell around those
existing services.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from src.client_database import archive_client, create_client, list_clients, restore_client
from src.database import DatabaseError, get_all_invoices, initialise_database
from src.database_integration import store_invoice_result
from src.duplicate_detector import find_duplicate_matches
from src.excel_writer import write_invoices_to_excel
from src.llm_extractor import DEFAULT_PROVIDER, PROVIDERS, ExtractionError, extract_invoice
from src.models import InvoiceExtraction, LineItem
from src.settings import get_setting, save_settings

initialise_database()
st.set_page_config(page_title="OCR5 Bookkeeping", page_icon="🧾", layout="wide", initial_sidebar_state="collapsed")

# ---------- visual system ----------
st.markdown("""
<style>
[data-testid="stSidebar"] {display:none;}
.block-container {max-width:1180px; padding-top:3.5rem; padding-bottom:5rem;}
.hero {text-align:center; padding:3.5rem 1rem 2rem;}
.brand {font-size:1rem; font-weight:700; letter-spacing:.18em; text-transform:uppercase; opacity:.55; margin-bottom:2rem;}
.hero h1 {font-size:3rem; line-height:1.05; margin:0 0 .7rem; font-weight:750; letter-spacing:-.045em;}
.hero p {font-size:1.05rem; opacity:.6; margin:0 auto 2rem; max-width:620px;}
.search-wrap {max-width:700px; margin:0 auto 1.5rem;}
.search-wrap input {font-size:1.1rem !important; padding:1rem 1.1rem !important;}
.card-title {font-size:1.1rem; font-weight:700; margin-bottom:.2rem;}
.card-meta {opacity:.58; font-size:.88rem;}
.section-label {font-size:.75rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase; opacity:.48; margin:2rem 0 .8rem;}
.workspace-head {display:flex; align-items:flex-end; justify-content:space-between; margin-bottom:1.5rem;}
.workspace-kicker {font-size:.78rem; letter-spacing:.1em; text-transform:uppercase; opacity:.5; font-weight:700;}
.workspace-title {font-size:2.5rem; font-weight:750; letter-spacing:-.04em; margin:.2rem 0 0;}
.context {padding:.7rem 1rem; border:1px solid rgba(128,128,128,.22); border-radius:999px; opacity:.7; display:inline-block;}
div[data-testid="stButton"] button {border-radius:14px; min-height:52px; font-weight:650;}
.client-card div[data-testid="stButton"] button, .year-card div[data-testid="stButton"] button {text-align:left; justify-content:flex-start;}
.empty {text-align:center; padding:3rem 1rem; opacity:.55;}
</style>
""", unsafe_allow_html=True)


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


def _client_name(client: dict) -> str:
    return client.get("company_name") or client.get("name") or f"Client {client.get('id', '')}"


def _reset_invoice_state() -> None:
    for key, value in {
        "results": [], "overrides": {}, "saved_indexes": set(),
        "source_images": {}, "duplicate_confirmations": set(),
        "invoice_history_snapshot": [],
    }.items():
        st.session_state[key] = value


for key, default in {
    "stage": "clients", "active_client_id": None, "selected_year": None,
    "client_query": "", "year_query": "", "results": [], "overrides": {},
    "saved_indexes": set(), "source_images": {}, "duplicate_confirmations": set(),
    "invoice_history_snapshot": [],
}.items():
    st.session_state.setdefault(key, default)

clients = _load_clients()
client_map = {int(c["id"]): c for c in clients}


def go_clients() -> None:
    st.session_state.stage = "clients"
    st.session_state.active_client_id = None
    st.session_state.selected_year = None
    _reset_invoice_state()


def go_years(client_id: int) -> None:
    st.session_state.stage = "years"
    st.session_state.active_client_id = client_id
    st.session_state.selected_year = None
    st.session_state.year_query = ""
    _reset_invoice_state()


def go_workspace(year: int) -> None:
    st.session_state.stage = "workspace"
    st.session_state.selected_year = int(year)
    _reset_invoice_state()

# ---------- clients ----------
if st.session_state.stage == "clients":
    st.markdown('<div class="hero"><div class="brand">OCR5</div><h1>Who are you working on?</h1><p>Your bookkeeping workspace starts with a client. Search below or create a new one.</p></div>', unsafe_allow_html=True)
    with st.container():
        st.markdown('<div class="search-wrap">', unsafe_allow_html=True)
        query = st.text_input("Search clients", placeholder="Search clients...", label_visibility="collapsed", key="client_search")
        st.markdown('</div>', unsafe_allow_html=True)

    q = query.strip().lower()
    matches = [c for c in clients if not q or q in _client_name(c).lower() or q in str(c.get("name", "")).lower() or q in str(c.get("email", "")).lower()]
    if matches:
        st.markdown('<div class="section-label">Clients</div>', unsafe_allow_html=True)
        for client in matches:
            cid = int(client["id"])
            title = _client_name(client)
            contact = client.get("email") or client.get("phone") or "Bookkeeping workspace"
            with st.container(border=True):
                left, right = st.columns([5, 1])
                with left:
                    st.markdown(f'<div class="card-title">{title}</div><div class="card-meta">{contact}</div>', unsafe_allow_html=True)
                with right:
                    if st.button("Open →", key=f"open_client_{cid}", use_container_width=True):
                        go_years(cid)
                        st.rerun()
    else:
        st.markdown('<div class="empty">No clients match that search.</div>', unsafe_allow_html=True)

    st.divider()
    with st.expander("+ Add a new client"):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Client name *", placeholder="John Murphy Ltd", key="new_client_name")
            company = st.text_input("Company name", placeholder="Optional", key="new_client_company")
            email = st.text_input("Email", key="new_client_email")
        with c2:
            phone = st.text_input("Phone", key="new_client_phone")
            address = st.text_area("Address", key="new_client_address")
        if st.button("Create client", type="primary"):
            if not name.strip():
                st.error("Client name is required.")
            else:
                try:
                    created = create_client(name.strip(), company.strip(), email.strip(), phone.strip(), address.strip())
                    go_years(int(created["id"]))
                    st.rerun()
                except DatabaseError as exc:
                    st.error(str(exc))

    st.stop()

# ---------- year selection ----------
active_client = client_map.get(int(st.session_state.active_client_id))
if not active_client:
    go_clients()
    st.rerun()

if st.session_state.stage == "years":
    title = _client_name(active_client)
    st.markdown(f'<div class="hero"><div class="brand">OCR5 · CLIENT</div><h1>{title}</h1><p>Select the financial year you want to work on.</p></div>', unsafe_allow_html=True)
    a, b = st.columns([5, 1])
    with a:
        query = st.text_input("Search years", placeholder="Search years...", label_visibility="collapsed", key="year_search")
    with b:
        if st.button("← Clients", use_container_width=True):
            go_clients(); st.rerun()

    years = set(range(datetime.now().year, datetime.now().year - 7, -1))
    try:
        history = get_all_invoices(client_id=int(active_client["id"]))
        for row in history:
            if len(row) > 2 and row[2]:
                try:
                    years.add(pd.Timestamp(row[2]).year)
                except Exception:
                    pass
    except Exception:
        history = []
    q = query.strip()
    filtered_years = sorted([y for y in years if not q or q in str(y)], reverse=True)

    st.markdown('<div class="section-label">Financial years</div>', unsafe_allow_html=True)
    for year in filtered_years:
        count = 0
        total = 0.0
        for row in history:
            try:
                if pd.Timestamp(row[2]).year == year:
                    count += 1
                    total += float(row[3] or 0)
            except Exception:
                continue
        with st.container(border=True):
            left, right = st.columns([5, 1])
            with left:
                st.markdown(f'<div class="card-title">{year}</div><div class="card-meta">{count} invoice{\"s\" if count != 1 else \"\"} · {total:,.2f} tracked</div>', unsafe_allow_html=True)
            with right:
                if st.button("Open →", key=f"open_year_{year}", use_container_width=True):
                    go_workspace(year); st.rerun()
    st.stop()

# ---------- workspace ----------
year = int(st.session_state.selected_year)
title = _client_name(active_client)
st.markdown(f'<div class="workspace-head"><div><div class="workspace-kicker">{title} · Financial year {year}</div><div class="workspace-title">Bookkeeping workspace</div></div><div class="context">Client + year locked</div></div>', unsafe_allow_html=True)

nav1, nav2, nav3 = st.columns(3)
with nav1:
    if st.button("← Change year", use_container_width=True):
        go_years(int(active_client["id"])); st.rerun()
with nav2:
    if st.button("Clients", use_container_width=True):
        go_clients(); st.rerun()
with nav3:
    if st.button("Manage client", use_container_width=True):
        st.session_state.show_manage = True

if st.session_state.get("show_manage"):
    with st.expander("Manage client", expanded=True):
        st.write(title)
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Archive client", disabled=False):
                try:
                    archive_client(int(active_client["id"]))
                    go_clients(); st.rerun()
                except DatabaseError as exc:
                    st.error(str(exc))
        with c2:
            if active_client.get("archived_at") and st.button("Restore client"):
                try:
                    restore_client(int(active_client["id"]))
                    st.rerun()
                except DatabaseError as exc:
                    st.error(str(exc))

# Settings are deliberately tucked away so the client/year flow remains the first experience.
with st.expander("⚙ Settings"):
    provider_names = list(PROVIDERS.keys())
    saved_provider = get_setting("OCR5_PROVIDER", DEFAULT_PROVIDER)
    if saved_provider not in PROVIDERS:
        saved_provider = DEFAULT_PROVIDER
    provider = st.selectbox("AI provider", provider_names, index=provider_names.index(saved_provider))
    env_name = PROVIDERS[provider]["env_var"]
    api_key = st.text_input("AI API key", value=get_setting("OCR5_API_KEY") or _secret(env_name), type="password")
    supabase_url = st.text_input("Supabase URL", value=get_setting("SUPABASE_URL") or _secret("SUPABASE_URL"))
    supabase_key = st.text_input("Supabase key", value=get_setting("SUPABASE_KEY") or _secret("SUPABASE_KEY"), type="password")
    if st.button("Save settings"):
        save_settings(provider=provider, api_key=api_key, supabase_url=supabase_url, supabase_key=supabase_key)
        st.success("Settings saved.")
        st.rerun()
    if supabase_url and supabase_key:
        os.environ["SUPABASE_URL"] = supabase_url
        os.environ["SUPABASE_KEY"] = supabase_key
        database_configured = True
    else:
        database_configured = False
    active_key = api_key

st.markdown("### Add invoices")
if not active_key:
    st.warning("Add your AI API key in Settings before processing invoices.")
uploaded_files = st.file_uploader("Upload invoice photos", type=["jpg", "jpeg", "png", "heic", "heif", "bmp", "tiff", "webp"], accept_multiple_files=True, label_visibility="collapsed")
process_clicked = st.button("Process invoices", type="primary", disabled=not uploaded_files or not active_key, use_container_width=True)

if process_clicked and uploaded_files:
    st.session_state.results = []
    st.session_state.overrides = {}
    st.session_state.saved_indexes = set()
    st.session_state.source_images = {}
    st.session_state.duplicate_confirmations = set()
    if database_configured:
        try:
            st.session_state.invoice_history_snapshot = get_all_invoices(client_id=int(active_client["id"]))
        except Exception:
            st.session_state.invoice_history_snapshot = []
    results = []
    for uploaded_file in uploaded_files:
        with st.status(f"Processing {uploaded_file.name}...", expanded=True) as status:
            image_bytes = uploaded_file.getvalue()
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded_file.name).suffix) as tmp:
                tmp.write(image_bytes); tmp_path = tmp.name
            try:
                result = extract_invoice(tmp_path, api_key=active_key, provider=provider)
                result.source_file = uploaded_file.name
                results.append(result)
                idx = len(results) - 1
                st.session_state.source_images[idx] = {"bytes": image_bytes, "mime_type": uploaded_file.type or "application/octet-stream"}
                status.update(label="Extraction complete — review below", state="complete")
            except (ExtractionError, Exception) as exc:
                status.update(label=f"Failed: {uploaded_file.name}", state="error")
                st.error(str(exc))
    st.session_state.results = results


def _edited(idx: int, result: InvoiceExtraction) -> InvoiceExtraction:
    overrides = st.session_state.overrides.setdefault(idx, {})
    field = type(result.date)
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
        line_items=result.line_items, warnings=result.warnings, raw_text=result.raw_text, validation_warnings=result.validation_warnings,
    )

if st.session_state.results:
    st.markdown("### Review & approve")
    for idx, result in enumerate(st.session_state.results):
        overrides = st.session_state.overrides.setdefault(idx, {})
        with st.container(border=True):
            st.markdown(f"**{result.source_file}**")
            cols = st.columns(4)
            for col, label, key, value in zip(cols, ["Supplier", "Invoice number", "Date", "Currency"], ["supplier", "invoice_number", "date", "currency"], [result.supplier.value, result.invoice_number.value, result.date.value, result.currency]):
                with col:
                    overrides[key] = st.text_input(label, value=overrides.get(key, value or ""), key=f"{key}_{idx}")
            cols2 = st.columns(4)
            for col, label, key, value in zip(cols2, ["Subtotal", "VAT amount", "VAT rate %", "Final total"], ["subtotal", "vat_amount", "vat_rate", "amount"], [result.subtotal.value, result.vat_amount.value, result.vat_rate.value, result.amount.value]):
                with col:
                    overrides[key] = st.text_input(label, value=overrides.get(key, value or ""), key=f"{key}_{idx}")
            try:
                invoice_date = pd.Timestamp(overrides.get("date", result.date.value or ""))
                if invoice_date.year != year:
                    st.warning(f"This invoice is dated {invoice_date.year}, but you are working in {year}. Check the date before saving.")
            except Exception:
                pass
            overrides["approved"] = st.checkbox("Approved for export", value=not result.needs_review, key=f"approve_{idx}", disabled=idx in st.session_state.saved_indexes)

    if database_configured:
        approved = [i for i, r in enumerate(st.session_state.results) if st.session_state.overrides.get(i, {}).get("approved", not r.needs_review) and i not in st.session_state.saved_indexes]
        if st.button(f"💾 Save {len(approved)} approved invoice(s)", type="primary", disabled=not approved, use_container_width=True):
            errors = []
            for idx in approved:
                edited = _edited(idx, st.session_state.results[idx])
                try:
                    store_invoice_result(edited, image_bytes=st.session_state.source_images.get(idx, {}).get("bytes"), mime_type=st.session_state.source_images.get(idx, {}).get("mime_type", "application/octet-stream"), client_id=int(active_client["id"]))
                    st.session_state.saved_indexes.add(idx)
                except DatabaseError as exc:
                    errors.append(f"{edited.source_file}: {exc}")
            if errors:
                st.error("Some invoices could not be saved:\n" + "\n".join(errors))
            else:
                st.success(f"Saved {len(approved)} invoice(s) to {title} · {year}.")
            st.rerun()

# ---------- year-specific history ----------
st.divider()
st.markdown(f"### {year} invoice history")
if database_configured:
    try:
        history = get_all_invoices(client_id=int(active_client["id"]))
        rows = []
        for r in history:
            try:
                if pd.Timestamp(r[2]).year != year:
                    continue
            except Exception:
                continue
            rows.append({"Invoice": r[8], "Date": r[2], "Supplier": r[1], "Amount": r[3], "Currency": r[4]})
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True)
            total = pd.to_numeric(df["Amount"], errors="coerce").fillna(0).sum()
            st.metric("Year spend", f"{total:,.2f}")
            export_rows = []
            for idx, result in enumerate(st.session_state.results):
                if st.session_state.overrides.get(idx, {}).get("approved"):
                    export_rows.append(_edited(idx, result))
            if export_rows and st.button("Prepare Excel export"):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                    write_invoices_to_excel(export_rows, tmp.name)
                    st.download_button("Download invoices.xlsx", data=open(tmp.name, "rb").read(), file_name=f"{title.replace(' ', '_')}_{year}_invoices.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.info(f"No invoices have been saved for {year} yet.")
    except Exception as exc:
        st.warning(f"Could not load invoice history: {exc}")
else:
    st.info("Connect Supabase in Settings to save and view this client's invoices.")
