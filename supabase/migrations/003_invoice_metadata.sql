-- OCR5 invoice metadata: invoice number and VAT details.
-- Run once in the Supabase SQL editor.

alter table public.invoices
  add column if not exists invoice_number text,
  add column if not exists subtotal numeric,
  add column if not exists vat_amount numeric,
  add column if not exists vat_rate numeric;

create index if not exists invoices_invoice_number_idx
  on public.invoices (invoice_number);
