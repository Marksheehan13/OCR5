"""OCR5 invoice history and dashboard."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.database import DatabaseError, get_all_invoices
from src.storage import StorageError, create_invoice_image_url
from src.ui import apply_theme, page_header

st.set_page_config(page_title="OCR5 · Invoice History", page_icon="🧾", layout="wide")
apply_theme()
page_header(
    "OCR5 · Bookkeeping",
    "Invoice history",
    "Search, analyse and review invoices approved and saved to your bookkeeping workspace.",
)

try:
    invoices = get_all_invoices()
except DatabaseError as exc:
    st.warning(
        f"{exc}\n\nAdd SUPABASE_URL and SUPABASE_KEY on the main page or in Streamlit secrets to enable invoice history."
    )
    st.stop()

if not invoices:
    st.markdown(
        '<div class="ocr5-panel"><strong>No approved invoices yet.</strong><br>'
        '<span style="opacity:.58">Upload and approve your first invoice to start building the record.</span></div>',
        unsafe_allow_html=True,
    )
    st.stop()


df = pd.DataFrame(
    invoices,
    columns=[
        "ID", "Supplier", "Invoice Date", "Amount", "Currency", "Confidence", "Image", "Created At",
        "Invoice Number", "Subtotal", "VAT Amount", "VAT Rate",
    ],
)
for column in ["Amount", "Subtotal", "VAT Amount", "VAT Rate", "Confidence"]:
    df[column] = pd.to_numeric(df[column], errors="coerce")
df["Created At"] = pd.to_datetime(df["Created At"], errors="coerce", utc=True)

st.markdown('<div class="ocr5-section-label">Overview</div>', unsafe_allow_html=True)
metric_cols = st.columns(4)
with metric_cols[0]:
    st.metric("Total invoices", f"{len(df):,}")
with metric_cols[1]:
    st.metric("Total value", f"€{df['Amount'].sum():,.2f}")
with metric_cols[2]:
    avg_conf = df["Confidence"].mean()
    st.metric("Average confidence", f"{avg_conf:.1f}%" if pd.notna(avg_conf) else "—")
with metric_cols[3]:
    current_month = pd.Timestamp.now(tz="UTC").to_period("M")
    month_mask = df["Created At"].dt.to_period("M") == current_month
    st.metric("This month", f"€{df.loc[month_mask, 'Amount'].sum():,.2f}")

currencies = sorted(df["Currency"].dropna().astype(str).unique())
if len(currencies) > 1:
    st.warning(
        "Multiple currencies are present. Total-value metrics combine currencies and should not be treated as a converted total."
    )

st.markdown('<div class="ocr5-section-label">Spend overview</div>', unsafe_allow_html=True)
chart_col1, chart_col2 = st.columns(2)
with chart_col1:
    st.markdown("**Invoice count by supplier**")
    st.bar_chart(df["Supplier"].fillna("Unknown").value_counts().head(10))
with chart_col2:
    st.markdown("**Spend by supplier**")
    spend_by_supplier = (
        df.assign(Supplier=df["Supplier"].fillna("Unknown"))
        .groupby("Supplier")["Amount"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
    )
    st.bar_chart(spend_by_supplier)

st.markdown('<div class="ocr5-section-label">Invoice records</div>', unsafe_allow_html=True)
filter_cols = st.columns([2, 1, 1, 1])
with filter_cols[0]:
    search = st.text_input("Search supplier", placeholder="e.g. Tesco")
with filter_cols[1]:
    currency_filter = st.selectbox("Currency", ["All"] + currencies)
with filter_cols[2]:
    min_conf = st.number_input("Min confidence", min_value=0, max_value=100, value=0, step=5)
with filter_cols[3]:
    sort_order = st.selectbox("Sort", ["Newest", "Oldest", "Highest value", "Lowest value"])

filtered = df.copy()
if search:
    filtered = filtered[filtered["Supplier"].fillna("").str.contains(search, case=False, na=False)]
if currency_filter != "All":
    filtered = filtered[filtered["Currency"].astype(str) == currency_filter]
filtered = filtered[filtered["Confidence"].fillna(0) >= min_conf]
if sort_order == "Newest":
    filtered = filtered.sort_values("Created At", ascending=False)
elif sort_order == "Oldest":
    filtered = filtered.sort_values("Created At", ascending=True)
elif sort_order == "Highest value":
    filtered = filtered.sort_values("Amount", ascending=False)
else:
    filtered = filtered.sort_values("Amount", ascending=True)

st.caption(f"Showing {len(filtered):,} of {len(df):,} invoices")
if filtered.empty:
    st.markdown(
        '<div class="ocr5-panel"><strong>No invoices match these filters.</strong><br>'
        '<span style="opacity:.58">Try widening your search or resetting the filters.</span></div>',
        unsafe_allow_html=True,
    )
else:
    display_df = filtered[
        ["ID", "Invoice Number", "Supplier", "Invoice Date", "Subtotal", "VAT Amount", "VAT Rate", "Amount", "Currency", "Confidence", "Created At"]
    ].copy()
    display_df["Created At"] = display_df["Created At"].dt.strftime("%Y-%m-%d %H:%M")
    st.dataframe(display_df, width="stretch", hide_index=True)

    st.markdown('<div class="ocr5-section-label">Invoice viewer</div>', unsafe_allow_html=True)
    selected_id = st.selectbox(
        "Select an invoice to inspect",
        filtered["ID"].tolist(),
        format_func=lambda invoice_id: (
            f"#{invoice_id} — {filtered.loc[filtered['ID'] == invoice_id, 'Supplier'].iloc[0] or 'Unknown'} — "
            f"{filtered.loc[filtered['ID'] == invoice_id, 'Currency'].iloc[0] or ''} "
            f"{filtered.loc[filtered['ID'] == invoice_id, 'Amount'].iloc[0]:,.2f}"
        ),
    )
    selected = filtered[filtered["ID"] == selected_id].iloc[0]
    detail_cols = st.columns([1, 1, 2])
    with detail_cols[0]:
        st.write(f"**Supplier**\n{selected['Supplier'] or '—'}")
        st.write(f"**Invoice number**\n{selected['Invoice Number'] or '—'}")
        st.write(f"**Invoice date**\n{selected['Invoice Date'] or '—'}")
    with detail_cols[1]:
        for label, column in [("Subtotal", "Subtotal"), ("VAT amount", "VAT Amount"), ("VAT rate", "VAT Rate"), ("Total", "Amount")]:
            value = selected[column]
            suffix = "%" if column == "VAT Rate" else ""
            st.write(f"**{label}**\n{value:,.2f}{suffix}" if pd.notna(value) else f"**{label}**\n—")
        st.write(f"**Currency**\n{selected['Currency'] or '—'}")
    with detail_cols[2]:
        try:
            image_url = create_invoice_image_url(str(selected["Image"]))
            if image_url:
                st.image(image_url, caption="Stored invoice", width="stretch")
            else:
                st.info("No stored image is available for this invoice.")
        except StorageError as exc:
            st.warning(f"Could not load the stored invoice image: {exc}")
