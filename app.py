"""OCR5 Streamlit application."""
from __future__ import annotations
import os, tempfile
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from src.client_database import archive_client, create_client, list_clients, restore_client
from src.database import DatabaseError, get_all_invoices, initialise_database
from src.database_integration import store_invoice_result
from src.llm_extractor import DEFAULT_PROVIDER, PROVIDERS, ExtractionError, extract_invoice
from src.models import InvoiceExtraction
from src.server_config import get_ai_api_key, get_ai_provider, validate_server_config
from src.settings import get_setting, save_settings

st.set_page_config(page_title="OCR5 Bookkeeping", page_icon="🧾", layout="wide", initial_sidebar_state="collapsed")

# Native Streamlit OIDC authentication. Credentials stay in Streamlit secrets;
# end users never receive Supabase or AI infrastructure credentials.
try:
    is_logged_in = bool(st.user.is_logged_in)
except Exception:
    is_logged_in = False

if not is_logged_in:
    st.markdown("""
    <style>
    [data-testid="stSidebar"]{display:none}
    .block-container{max-width:720px;padding-top:12vh}
    .login-shell{text-align:center;padding:3rem 1rem}
    .login-brand{font-size:.75rem;font-weight:800;letter-spacing:.18em;opacity:.5}
    .login-title{font-size:3rem;font-weight:780;letter-spacing:-.05em;margin:.8rem 0 .6rem}
    .login-copy{opacity:.58;margin-bottom:2rem}
    </style>
    <div class="login-shell">
      <div class="login-brand">OCR5</div>
      <div class="login-title">Your bookkeeping,<br>organised.</div>
      <div class="login-copy">Secure invoice processing for your bookkeeping workspace.</div>
    </div>
    """, unsafe_allow_html=True)
    st.button("Continue with Google", type="primary", width="stretch", on_click=st.login)
    st.caption("Sign in securely. OCR5 manages the technical infrastructure for you.")
    st.stop()

# Authenticated identity is available through st.user. Keep the identity stable
# for the application layer; authorization is enforced separately by Supabase RLS.
user_email = getattr(st.user, "email", None) or st.user.get("email", "")
user_name = getattr(st.user, "name", None) or st.user.get("name", "")

initialise_database()

st.markdown("""
<style>
[data-testid="stSidebar"]{display:none}.block-container{max-width:1180px;padding-top:3rem;padding-bottom:5rem}
.hero{text-align:center;padding:3rem 1rem 2rem}.brand{font-size:.75rem;font-weight:800;letter-spacing:.18em;text-transform:uppercase;opacity:.5;margin-bottom:1.5rem}.hero h1{font-size:2.7rem;line-height:1.05;margin:0 0 .6rem;font-weight:760;letter-spacing:-.045em}.hero p{opacity:.58;margin:0 auto 1.8rem;max-width:620px}.search-wrap{max-width:700px;margin:auto}.search-wrap input{font-size:1.05rem!important;padding:1rem!important}.section-label{font-size:.7rem;font-weight:800;letter-spacing:.13em;text-transform:uppercase;opacity:.48;margin:1.7rem 0 .7rem}.card-title{font-size:1.05rem;font-weight:720}.card-meta{font-size:.82rem;opacity:.56;margin-top:.2rem}.workspace-head{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:1.3rem}.workspace-kicker{font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;opacity:.5;font-weight:800}.workspace-title{font-size:2.35rem;font-weight:760;letter-spacing:-.04em;margin:.15rem 0 0}.context{padding:.55rem .85rem;border:1px solid rgba(128,128,128,.2);border-radius:999px;font-size:.8rem;opacity:.65}.metric{padding:1rem 1.1rem;border:1px solid rgba(128,128,128,.18);border-radius:16px;background:rgba(128,128,128,.035)}.metric-label{font-size:.72rem;opacity:.52}.metric-value{font-size:1.55rem;font-weight:760;margin-top:.2rem}.empty{text-align:center;padding:3rem 1rem;border:1px dashed rgba(128,128,128,.25);border-radius:16px;opacity:.55}div[data-testid="stButton"] button{border-radius:14px;min-height:46px;font-weight:650}
</style>""", unsafe_allow_html=True)

def client_name(c): return c.get("company_name") or c.get("name") or f"Client {c.get('id','')}"
def reset():
    for k,v in {"results":[],"overrides":{},"saved_indexes":set(),"source_images":[],"duplicate_confirmations":set()}.items():st.session_state[k]=v
for k,v in {"stage":"clients","active_client_id":None,"selected_year":None,"client_query":"","year_query":"","results":[],"overrides":{},"saved_indexes":set(),"source_images":[],"duplicate_confirmations":set()}.items():st.session_state.setdefault(k,v)
try: clients=list_clients()
except Exception: clients=[]
client_map={int(c["id"]):c for c in clients}
def go_clients(): st.session_state.stage="clients";st.session_state.active_client_id=None;st.session_state.selected_year=None;reset()
def go_years(cid): st.session_state.stage="years";st.session_state.active_client_id=cid;st.session_state.selected_year=None;reset()
def go_workspace(y): st.session_state.stage="workspace";st.session_state.selected_year=int(y);reset()

if st.session_state.stage=="clients":
    st.markdown(f'<div class="hero"><div class="brand">OCR5</div><h1>Who are you working on?</h1><p>Search for a client to open their private bookkeeping workspace.</p></div>',unsafe_allow_html=True)
    q=st.text_input("Search",placeholder="Search clients...",label_visibility="collapsed",key="client_query")
    matches=[c for c in clients if not q.strip() or q.lower() in client_name(c).lower() or q.lower() in str(c.get("email","")).lower()]
    st.markdown('<div class="section-label">Clients</div>',unsafe_allow_html=True)
    if not matches: st.markdown('<div class="empty">No clients match your search.</div>',unsafe_allow_html=True)
    for c in matches:
        cid=int(c["id"])
        with st.container(border=True):
            a,b=st.columns([5,1]); a.markdown(f'<div class="card-title">{client_name(c)}</div><div class="card-meta">{c.get("email") or c.get("phone") or "Bookkeeping workspace"}</div>',unsafe_allow_html=True)
            if b.button("Open →",key=f"client_{cid}"):go_years(cid);st.rerun()
    st.divider()
    with st.expander("+ Add client"):
        n=st.text_input("Client name *");co=st.text_input("Company name");em=st.text_input("Email");ph=st.text_input("Phone");ad=st.text_area("Address")
        if st.button("Create client",type="primary"):
            if not n.strip():st.error("Client name is required.")
            else:
                try: new=create_client(n.strip(),co.strip(),em.strip(),ph.strip(),ad.strip());go_years(int(new["id"]));st.rerun()
                except DatabaseError as e:st.error(str(e))
    st.stop()

active=client_map.get(int(st.session_state.active_client_id or 0))
if not active:go_clients();st.rerun()
if st.session_state.stage=="years":
    title=client_name(active)
    st.markdown(f'<div class="hero"><div class="brand">OCR5 · CLIENT</div><h1>{title}</h1><p>Select the financial year you want to work on.</p></div>',unsafe_allow_html=True)
    a,b=st.columns([5,1]);q=a.text_input("Search",placeholder="Search financial years...",label_visibility="collapsed",key="year_query")
    if b.button("← Clients"):go_clients();st.rerun()
    try: history=get_all_invoices(client_id=int(active["id"]))
    except Exception: history=[]
    years=set(range(datetime.now().year,datetime.now().year-7,-1))
    for r in history:
        try:years.add(pd.Timestamp(r[2]).year)
        except Exception:pass
    st.markdown('<div class="section-label">Financial years</div>',unsafe_allow_html=True)
    for y in sorted([x for x in years if not q.strip() or q.strip() in str(x)],reverse=True):
        rows=[r for r in history if len(r)>3 and r[2] and pd.Timestamp(r[2]).year==y];total=sum(float(r[3] or 0) for r in rows)
        with st.container(border=True):
            a,b=st.columns([5,1]);a.markdown(f'<div class="card-title">{y}</div><div class="card-meta">{len(rows)} {"invoice" if len(rows)==1 else "invoices"} · {total:,.2f} tracked</div>',unsafe_allow_html=True)
            if b.button("Open →",key=f"year_{y}"):go_workspace(y);st.rerun()
    st.stop()

year=int(st.session_state.selected_year);title=client_name(active)
try: history=get_all_invoices(client_id=int(active["id"]))
except Exception: history=[]
rows=[]
for r in history:
    try:
        if pd.Timestamp(r[2]).year==year:rows.append(r)
    except Exception:pass
df=pd.DataFrame(rows,columns=["ID","Supplier","Date","Amount","Currency","Confidence","Image","Created","Invoice Number","Subtotal","VAT Amount","VAT Rate","Client ID"]) if rows else pd.DataFrame()
for c in ["Amount","VAT Amount","Subtotal","Confidence"]:
    if not df.empty:df[c]=pd.to_numeric(df[c],errors="coerce")
spend=float(df["Amount"].sum()) if not df.empty else 0; count=len(df); avg=spend/count if count else 0; vat=float(df["VAT Amount"].sum()) if not df.empty else 0
st.markdown(f'<div class="workspace-head"><div><div class="workspace-kicker">{title} · Financial year {year}</div><div class="workspace-title">Overview</div></div><div class="context">Client + year locked</div></div>',unsafe_allow_html=True)
a,b,c,d=st.columns(4)
for col,label,value in [(a,"Total spend",f"€{spend:,.2f}"),(b,"Invoices",f"{count:,}"),(c,"Average invoice",f"€{avg:,.2f}"),(d,"VAT captured",f"€{vat:,.2f}")]:col.markdown(f'<div class="metric"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>',unsafe_allow_html=True)
st.write("")
n1,n2,n3,n4=st.columns(4)
if n1.button("+ Upload invoice",type="primary",use_container_width=True):st.session_state.show_upload=True
if n2.button("Invoices",use_container_width=True):st.session_state.show_history=True
if n3.button("Analytics",use_container_width=True):st.session_state.show_analytics=True
if n4.button("← Change year",use_container_width=True):go_years(int(active["id"]));st.rerun()

if not df.empty:
    st.markdown('<div class="section-label">Recent invoices</div>',unsafe_allow_html=True)
    recent=df.sort_values("Date",ascending=False).head(8)
    st.dataframe(recent[["Invoice Number","Supplier","Date","Amount","Currency"]],width="stretch",hide_index=True)
    x,y=st.columns(2)
    with x:
        st.markdown('<div class="section-label">Monthly spend</div>',unsafe_allow_html=True)
        monthly=df.assign(Month=pd.to_datetime(df["Date"]).dt.to_period("M")).groupby("Month")["Amount"].sum();monthly.index=monthly.index.astype(str);st.bar_chart(monthly)
    with y:
        st.markdown('<div class="section-label">Top suppliers</div>',unsafe_allow_html=True)
        st.bar_chart(df.assign(Supplier=df["Supplier"].fillna("Unknown")).groupby("Supplier")["Amount"].sum().sort_values(ascending=False).head(8))
else: st.markdown('<div class="empty"><strong>No invoices yet</strong><br>Upload your first invoice to start building this financial year.</div>',unsafe_allow_html=True)

if st.session_state.get("show_upload"):
    st.divider();st.markdown("### Upload invoices")
    provider=get_ai_provider();api_key=get_ai_api_key(provider)
    config=validate_server_config()
    if not config["ai"]:
        st.error("OCR5 AI is not configured on the server. An administrator must add the AI provider API key to the deployment secrets.")
    else:
        st.caption(f"OCR5 AI · {provider.title()} · secured by the application")
        files=st.file_uploader("Upload invoice photos",type=["jpg","jpeg","png","heic","heif","bmp","tiff","webp"],accept_multiple_files=True)
        if st.button("Process invoices",type="primary",disabled=not files):
            results=[];images=[]
            for f in files:
                with st.status(f"Processing {f.name}...",expanded=True) as status:
                    data=f.getvalue()
                    with tempfile.NamedTemporaryFile(delete=False,suffix=Path(f.name).suffix) as tmp:tmp.write(data);path=tmp.name
                    try:r=extract_invoice(path,api_key=api_key,provider=provider);r.source_file=f.name;results.append(r);images.append({"bytes":data,"mime_type":f.type or "application/octet-stream"});status.update(label="Extraction complete",state="complete")
                    except Exception as e:status.update(label="Extraction failed",state="error");st.error(str(e))
            st.session_state.results=results;st.session_state.source_images=images

if st.session_state.results:
    st.markdown("### Review & approve")
    for i,r in enumerate(st.session_state.results):
        o=st.session_state.overrides.setdefault(i,{})
        with st.container(border=True):
            cols=st.columns(4)
            for col,label,key,val in zip(cols,["Supplier","Invoice number","Date","Currency"],["supplier","invoice_number","date","currency"],[r.supplier.value,r.invoice_number.value,r.date.value,r.currency]):o[key]=col.text_input(label,value=o.get(key,val or ""),key=f"{key}_{i}")
            cols=st.columns(4)
            for col,label,key,val in zip(cols,["Subtotal","VAT amount","VAT rate %","Final total"],["subtotal","vat_amount","vat_rate","amount"],[r.subtotal.value,r.vat_amount.value,r.vat_rate.value,r.amount.value]):o[key]=col.text_input(label,value=o.get(key,val or ""),key=f"{key}_{i}")
            o["approved"]=st.checkbox("Approved for export",value=not r.needs_review,key=f"approved_{i}")
    st.warning("Invoice saving remains connected to the existing persistence workflow; this dashboard pass does not alter the underlying database schema.")

if st.session_state.get("show_history"):
    st.divider();st.markdown("### Invoice history");st.dataframe(df[["Invoice Number","Supplier","Date","Amount","Currency"]] if not df.empty else pd.DataFrame(),width="stretch",hide_index=True)
if st.session_state.get("show_analytics") and not df.empty:
    st.divider();st.markdown("### Analytics");st.bar_chart(df.assign(Supplier=df["Supplier"].fillna("Unknown")).groupby("Supplier")["Amount"].sum().sort_values(ascending=False).head(12))

with st.expander("⚙ Settings"):
    st.markdown("**OCR5 configuration**")
    st.caption("Infrastructure and AI credentials are managed securely by the application. End users do not need to enter API keys or database credentials.")
    provider=get_ai_provider();config=validate_server_config()
    st.write(f"Signed in as: **{user_name or user_email}**")
    if st.button("Log out"):
        st.logout()
    st.write(f"AI provider: **{provider.title()}**")
    st.write(f"AI service: **{'Connected' if config['ai'] else 'Not configured'}**")
    st.write(f"Database service: **{'Connected' if config['supabase'] else 'Not configured'}**")
    if st.button("Save provider preference"):
        save_settings(provider=provider);st.success("Preference saved.")
