"""Client management persistence for OCR5."""
from __future__ import annotations
from .database import DatabaseError, _get_client, _rows, _COLUMNS
from .auth import organisation_id

def _org_id() -> str:
    client=_get_client(); value=organisation_id(client)
    if not value: raise DatabaseError("Your OCR5 account is not attached to an organisation yet.")
    return value

def create_client(name, company_name=None, email=None, phone=None, address=None)->dict:
    name=(name or "").strip()
    if not name: raise DatabaseError("Client name is required.")
    response=_get_client().table("clients").insert({"name":name,"company_name":(company_name or "").strip() or None,"email":(email or "").strip() or None,"phone":(phone or "").strip() or None,"address":(address or "").strip() or None,"organization_id":_org_id()}).execute()
    if not response.data: raise DatabaseError("Client was not returned after saving.")
    return response.data[0]

def list_clients(include_inactive=False)->list[dict]:
    q=_get_client().table("clients").select("id,name,company_name,email,phone,address,active,created_at,updated_at,organization_id")
    if not include_inactive:q=q.eq("active",True)
    return q.order("name").execute().data or []

def get_client(client_id:int)->dict|None:
    response=_get_client().table("clients").select("id,name,company_name,email,phone,address,active,created_at,updated_at,organization_id").eq("id",client_id).limit(1).execute()
    return response.data[0] if response.data else None

def update_client(client_id:int,**fields)->dict:
    allowed={"name","company_name","email","phone","address","active"}; values={k:v for k,v in fields.items() if k in allowed and v is not None}
    if "name" in values:
        values["name"]=str(values["name"]).strip()
        if not values["name"]:raise DatabaseError("Client name is required.")
    for key in ("company_name","email","phone","address"):
        if key in values:values[key]=str(values[key]).strip() or None
    if not values:raise DatabaseError("No client fields were supplied.")
    response=_get_client().table("clients").update(values).eq("id",client_id).execute()
    if not response.data:raise DatabaseError("Client was not found or could not be updated.")
    return response.data[0]

def archive_client(client_id:int)->dict:return update_client(client_id,active=False)
def restore_client(client_id:int)->dict:return update_client(client_id,active=True)
def client_invoice_count(client_id:int)->int:
    response=_get_client().table("invoices").select("id",count="exact").eq("client_id",client_id).execute(); return int(response.count or 0)
def get_client_invoices(client_id:int)->list[tuple]:
    response=_get_client().table("invoices").select(_COLUMNS).eq("client_id",client_id).order("created_at",desc=True).execute(); return _rows(response)
def get_client_analytics(client_id:int)->dict:
    invoices=get_client_invoices(client_id); amounts=[float(r[3]) for r in invoices if r[3] is not None]; vat=[float(r[10]) for r in invoices if r[10] is not None]
    return {"client_id":client_id,"invoice_count":len(invoices),"total_spend":sum(amounts),"total_vat":sum(vat),"average_invoice_value":sum(amounts)/len(amounts) if amounts else 0.0}
