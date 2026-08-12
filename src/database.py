"""Persistent storage layer for OCR5, backed by Supabase (Postgres)."""
from __future__ import annotations
from collections import defaultdict
import os
from supabase import create_client, Client
from .db_context import get_bound_client

class DatabaseError(Exception):
    """Raised when the database isn't configured or a request fails."""

def _get_client() -> Client:
    bound = get_bound_client()
    if bound is not None:
        return bound
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise DatabaseError("Supabase is not configured on the server.")
    return create_client(url, key)

def initialise_database() -> None:
    return None

def save_invoice(supplier, invoice_date, amount, currency, confidence, image_path, invoice_number=None, subtotal=None, vat_amount=None, vat_rate=None, client_id=None) -> int:
    if client_id is None: raise DatabaseError("A client must be selected before an invoice can be saved.")
    response = _get_client().table("invoices").insert({"client_id":client_id,"supplier":supplier,"invoice_date":invoice_date,"amount":amount,"currency":currency,"confidence":confidence,"image_path":image_path,"invoice_number":invoice_number,"subtotal":subtotal,"vat_amount":vat_amount,"vat_rate":vat_rate}).execute()
    if not response.data: raise DatabaseError("Invoice was not returned after saving.")
    return response.data[0]["id"]

def save_invoice_line_items(invoice_id: int, line_items) -> int:
    if not line_items: return 0
    def number(value):
        if value in (None,"","null"): return None
        try: return float(value)
        except (TypeError,ValueError): return None
    rows=[{"invoice_id":invoice_id,"description":item.description,"quantity":number(item.quantity),"unit_price":number(item.unit_price),"vat_rate":number(item.vat_rate),"line_total":number(item.line_total),"confidence":max(0,min(100,int(item.confidence or 0)))} for item in line_items]
    _get_client().table("invoice_line_items").insert(rows).execute(); return len(rows)

def get_invoice_line_items(invoice_id: int)->list[dict]:
    return _get_client().table("invoice_line_items").select("id,description,quantity,unit_price,vat_rate,line_total,confidence,created_at").eq("invoice_id",invoice_id).order("id").execute().data or []

def get_all_invoice_line_items()->list[dict]:
    return _get_client().table("invoice_line_items").select("id,invoice_id,description,quantity,unit_price,vat_rate,line_total,confidence,created_at").order("created_at",desc=True).execute().data or []

def get_client_invoice_line_items(client_id:int)->list[dict]:
    invoice_ids=[row[0] for row in get_all_invoices(client_id=client_id) if row[0] is not None]
    if not invoice_ids:return []
    return _get_client().table("invoice_line_items").select("id,invoice_id,description,quantity,unit_price,vat_rate,line_total,confidence,created_at").in_("invoice_id",invoice_ids).order("created_at",desc=True).execute().data or []

def get_invoice_analytics(client_id=None)->dict:
    invoices=get_all_invoices(client_id=client_id); items=get_client_invoice_line_items(client_id) if client_id is not None else get_all_invoice_line_items()
    amounts=[float(r[3]) for r in invoices if r[3] is not None]; vats=[float(r[10]) for r in invoices if r[10] is not None]; by_supplier=defaultdict(float); by_month=defaultdict(float)
    for r in invoices:
        if r[3] is None:continue
        by_supplier[r[1] or "Unknown supplier"]+=float(r[3])
        if r[2]:by_month[str(r[2])[:7]]+=float(r[3])
    return {"client_id":client_id,"invoice_count":len(invoices),"line_item_count":len(items),"total_spend":sum(amounts),"total_vat":sum(vats),"average_invoice_value":sum(amounts)/len(amounts) if amounts else 0.0,"spend_by_supplier":dict(sorted(by_supplier.items(),key=lambda x:x[1],reverse=True)),"spend_by_month":dict(sorted(by_month.items()))}

def get_supplier_item_analysis(client_id=None)->list[dict]:
    invoices={r[0]:(r[1] or "Unknown supplier") for r in get_all_invoices(client_id=client_id)}; groups={}
    items=get_client_invoice_line_items(client_id) if client_id is not None else get_all_invoice_line_items()
    for item in items:
        supplier=invoices.get(item["invoice_id"],"Unknown supplier"); description=" ".join(str(item.get("description") or "").lower().split())
        if not description:continue
        key=(supplier,description); group=groups.setdefault(key,{"supplier":supplier,"description":str(item.get("description") or "").strip(),"quantity":0.0,"line_count":0,"total_spend":0.0,"unit_prices":[]})
        if item.get("quantity") is not None:group["quantity"]+=float(item["quantity"])
        if item.get("line_total") is not None:group["total_spend"]+=float(item["line_total"])
        if item.get("unit_price") is not None:group["unit_prices"].append(float(item["unit_price"]))
        group["line_count"]+=1
    results=[]
    for group in groups.values():
        prices=group.pop("unit_prices"); group["average_unit_price"]=sum(prices)/len(prices) if prices else None; results.append(group)
    return sorted(results,key=lambda x:x["total_spend"],reverse=True)

def get_item_price_comparisons(client_id=None)->list[dict]:
    analysis=get_supplier_item_analysis(client_id); items=defaultdict(list)
    for row in analysis:
        if row["average_unit_price"] is not None:items[row["description"].lower()].append(row)
    comparisons=[]
    for suppliers in items.values():
        if len(suppliers)<2:continue
        prices=[r["average_unit_price"] for r in suppliers]; comparisons.append({"description":suppliers[0]["description"],"suppliers":suppliers,"lowest_price":min(prices),"highest_price":max(prices),"price_difference":max(prices)-min(prices)})
    return sorted(comparisons,key=lambda x:x["price_difference"],reverse=True)

_COLUMNS="id,supplier,invoice_date,amount,currency,confidence,image_path,created_at,invoice_number,subtotal,vat_amount,vat_rate,client_id"
def _rows(response):
    return [(r["id"],r["supplier"],r["invoice_date"],r["amount"],r["currency"],r["confidence"],r["image_path"],r["created_at"],r.get("invoice_number"),r.get("subtotal"),r.get("vat_amount"),r.get("vat_rate"),r.get("client_id")) for r in response.data]
def get_all_invoices(client_id=None):
    q=_get_client().table("invoices").select(_COLUMNS)
    if client_id is not None:q=q.eq("client_id",client_id)
    return _rows(q.order("created_at",desc=True).execute())
def search_supplier(supplier,client_id=None):
    q=_get_client().table("invoices").select(_COLUMNS).ilike("supplier",f"%{supplier}%")
    if client_id is not None:q=q.eq("client_id",client_id)
    return _rows(q.order("created_at",desc=True).execute())
