"""
database.py

Persistent storage layer for OCR5, backed by Supabase (Postgres).
"""

from __future__ import annotations

from collections import defaultdict
import os

from supabase import create_client, Client


class DatabaseError(Exception):
    """Raised when the database isn't configured or a request fails."""


def _get_client() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise DatabaseError("SUPABASE_URL and SUPABASE_KEY must be set to use invoice history storage.")
    return create_client(url, key)


def initialise_database() -> None:
    return None


def save_invoice(supplier: str | None, invoice_date: str | None, amount: float | None, currency: str,
                 confidence: int, image_path: str, invoice_number: str | None = None,
                 subtotal: float | None = None, vat_amount: float | None = None,
                 vat_rate: float | None = None, client_id: int | None = None) -> int:
    """Save an invoice, optionally scoped to a client."""
    if client_id is None:
        raise DatabaseError("A client must be selected before an invoice can be saved.")
    response = _get_client().table("invoices").insert({
        "client_id": client_id, "supplier": supplier, "invoice_date": invoice_date,
        "amount": amount, "currency": currency, "confidence": confidence,
        "image_path": image_path, "invoice_number": invoice_number,
        "subtotal": subtotal, "vat_amount": vat_amount, "vat_rate": vat_rate,
    }).execute()
    if not response.data:
        raise DatabaseError("Invoice was not returned after saving.")
    return response.data[0]["id"]


def save_invoice_line_items(invoice_id: int, line_items) -> int:
    if not line_items:
        return 0
    def number(value):
        if value in (None, "", "null"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    rows = [{
        "invoice_id": invoice_id, "description": item.description, "quantity": number(item.quantity),
        "unit_price": number(item.unit_price), "vat_rate": number(item.vat_rate),
        "line_total": number(item.line_total), "confidence": max(0, min(100, int(item.confidence or 0))),
    } for item in line_items]
    _get_client().table("invoice_line_items").insert(rows).execute()
    return len(rows)


def get_invoice_line_items(invoice_id: int) -> list[dict]:
    response = _get_client().table("invoice_line_items").select("id,description,quantity,unit_price,vat_rate,line_total,confidence,created_at").eq("invoice_id", invoice_id).order("id").execute()
    return response.data or []


def get_all_invoice_line_items() -> list[dict]:
    response = _get_client().table("invoice_line_items").select("id,invoice_id,description,quantity,unit_price,vat_rate,line_total,confidence,created_at").order("created_at", desc=True).execute()
    return response.data or []


def get_client_invoice_line_items(client_id: int) -> list[dict]:
    invoice_ids = [row[0] for row in get_all_invoices(client_id) if row[0] is not None]
    if not invoice_ids:
        return []
    response = _get_client().table("invoice_line_items").select("id,invoice_id,description,quantity,unit_price,vat_rate,line_total,confidence,created_at").in_("invoice_id", invoice_ids).order("created_at", desc=True).execute()
    return response.data or []


def get_invoice_analytics(client_id: int | None = None) -> dict:
    """Return database-backed invoice and line-item aggregates for one client."""
    invoices = get_all_invoices(client_id)
    items = get_client_invoice_line_items(client_id) if client_id is not None else get_all_invoice_line_items()
    valid_amounts = [float(row[3]) for row in invoices if row[3] is not None]
    valid_vat = [float(row[10]) for row in invoices if row[10] is not None]
    by_supplier = defaultdict(float)
    by_month = defaultdict(float)
    for row in invoices:
        if row[3] is None:
            continue
        supplier = row[1] or "Unknown supplier"
        by_supplier[supplier] += float(row[3])
        if row[2]:
            by_month[str(row[2])[:7]] += float(row[3])
    return {
        "client_id": client_id,
        "invoice_count": len(invoices), "line_item_count": len(items), "total_spend": sum(valid_amounts),
        "total_vat": sum(valid_vat), "average_invoice_value": sum(valid_amounts) / len(valid_amounts) if valid_amounts else 0.0,
        "spend_by_supplier": dict(sorted(by_supplier.items(), key=lambda x: x[1], reverse=True)),
        "spend_by_month": dict(sorted(by_month.items())),
    }


def get_supplier_item_analysis(client_id: int | None = None) -> list[dict]:
    """Aggregate purchased items by normalized description and supplier."""
    invoices = {row[0]: (row[1] or "Unknown supplier") for row in get_all_invoices(client_id)}
    groups = {}
    items = get_client_invoice_line_items(client_id) if client_id is not None else get_all_invoice_line_items()
    for item in items:
        supplier = invoices.get(item["invoice_id"], "Unknown supplier")
        description = " ".join(str(item.get("description") or "").lower().split())
        if not description:
            continue
        key = (supplier, description)
        group = groups.setdefault(key, {"supplier": supplier, "description": str(item.get("description") or "").strip(), "quantity": 0.0, "line_count": 0, "total_spend": 0.0, "unit_prices": []})
        if item.get("quantity") is not None:
            group["quantity"] += float(item["quantity"])
        if item.get("line_total") is not None:
            group["total_spend"] += float(item["line_total"])
        if item.get("unit_price") is not None:
            group["unit_prices"].append(float(item["unit_price"]))
        group["line_count"] += 1
    results = []
    for group in groups.values():
        prices = group.pop("unit_prices")
        group["average_unit_price"] = sum(prices) / len(prices) if prices else None
        results.append(group)
    return sorted(results, key=lambda x: x["total_spend"], reverse=True)


def get_item_price_comparisons(client_id: int | None = None) -> list[dict]:
    """Compare average unit prices for matching items across suppliers."""
    analysis = get_supplier_item_analysis(client_id)
    items = defaultdict(list)
    for row in analysis:
        if row["average_unit_price"] is not None:
            items[row["description"].lower()].append(row)
    comparisons = []
    for suppliers in items.values():
        if len(suppliers) < 2:
            continue
        prices = [row["average_unit_price"] for row in suppliers]
        comparisons.append({
            "description": suppliers[0]["description"], "suppliers": suppliers,
            "lowest_price": min(prices), "highest_price": max(prices), "price_difference": max(prices) - min(prices),
        })
    return sorted(comparisons, key=lambda x: x["price_difference"], reverse=True)


_COLUMNS = "id,supplier,invoice_date,amount,currency,confidence,image_path,created_at,invoice_number,subtotal,vat_amount,vat_rate,client_id"


def _rows(response) -> list[tuple]:
    return [(row["id"], row["supplier"], row["invoice_date"], row["amount"], row["currency"], row["confidence"], row["image_path"], row["created_at"], row.get("invoice_number"), row.get("subtotal"), row.get("vat_amount"), row.get("vat_rate"), row.get("client_id")) for row in response.data]


def get_all_invoices(client_id: int | None = None) -> list[tuple]:
    query = _get_client().table("invoices").select(_COLUMNS)
    if client_id is not None:
        query = query.eq("client_id", client_id)
    response = query.order("created_at", desc=True).execute()
    return _rows(response)


def search_supplier(supplier: str, client_id: int | None = None) -> list[tuple]:
    query = _get_client().table("invoices").select(_COLUMNS).ilike("supplier", f"%{supplier}%")
    if client_id is not None:
        query = query.eq("client_id", client_id)
    response = query.order("created_at", desc=True).execute()
    return _rows(response)


if __name__ == "__main__":
    initialise_database()
    print("OCR5 database is ready (Supabase-backed, table created via migration).")
