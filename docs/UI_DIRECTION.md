# OCR5 UI Direction

## Product direction

OCR5 is being evolved from a Streamlit OCR prototype into a standalone AI bookkeeping product. Streamlit remains the current development surface only; the visual system must therefore be portable to a future web frontend.

Target visual language: **AI-native finance SaaS** — inspired by the polish of modern fintech products, the accounting information architecture of established bookkeeping platforms, and the clarity of products such as Linear/Stripe-style interfaces.

The product should feel:

- slick
- modern
- calm
- trustworthy
- intelligent
- premium
- operational rather than flashy

## Non-negotiable product principle

**Do not compromise existing bookkeeping/OCR logic for visual changes.**

The existing extraction, validation, confidence scoring, duplicate detection, approval, Supabase persistence, source-image storage, line-item persistence, analytics, and Excel export behaviour are business logic. Future UI work must consume these capabilities rather than rewrite them.

## Current capabilities to preserve

- Multi-image invoice upload
- Multiple AI providers through the existing provider abstraction
- Invoice extraction into `InvoiceExtraction`
- Field-level confidence and validation state
- Line-item extraction and review
- Duplicate detection against stored invoices
- Explicit human approval before persistence
- Supabase invoice history
- Source image storage
- Invoice line-item persistence
- Database-backed invoice analytics
- Supplier/item analysis
- Item price comparison analysis
- Excel export
- Local/API-key settings flow

## Visual system

### Colour

Primary accent: `#635BFF`

Light background: `#F7F8FA`

Surface: `#FFFFFF`

Primary text: `#17181C`

Border: `#E5E7EB`

Dark navigation: `#111318`

Dark navigation surface: `#181B22`

Use semantic colours sparingly:

- green = verified/success
- amber = review/attention
- red = error/failure
- violet = AI/interactive accent

Avoid rainbow dashboards and excessive gradients.

### Typography

Use a clean sans-serif hierarchy. Large financial numbers should have strong visual weight. Secondary metadata should remain quiet. Avoid dense accounting-software typography.

### Surfaces

Use subtle borders rather than heavy shadows. Prefer generous whitespace, 10–16px radii, compact controls, and clear grouping.

## Information architecture

### Primary navigation

- Dashboard
- Invoices
- Expenses
- Suppliers

### Analysis

- Analytics
- Reports

### System

- Settings

## Dashboard concept

The dashboard should answer **“What needs my attention?”** before showing exhaustive financial data.

Priority blocks:

1. Attention / AI recommendations
2. Financial KPIs
3. Cash-flow or spend trend
4. Recent invoices
5. Supplier/spend breakdown

Avoid filling the dashboard with decorative charts that do not lead to an action.

## Invoice workspace

The invoice review screen is a core differentiator and should use a two-pane document intelligence layout:

**Left:** source invoice/receipt preview.

**Right:** extracted fields, confidence, warnings, validation and approval controls.

Confidence should be visual, not just a numeric label. Low-confidence or validation-problem fields should be immediately discoverable.

## AI interaction model

OCR5 should communicate what the AI knows and what requires human judgement.

Examples:

- `98% confidence` — quiet confirmation
- `Needs review` — visible attention state
- `Possible duplicate` — contextual warning with existing-record comparison
- `VAT discrepancy` — explainable validation warning

Do not expose raw model internals unless the user explicitly asks for them.

## Future standalone frontend

The future frontend should be implemented as a presentation layer over the existing Python/business-logic services. Do not move business rules into browser-only code merely to make the interface work.

Preferred future architecture:

`Web UI → API/service layer → existing OCR/domain logic → Supabase/storage`

The Streamlit app remains a safe development/demo surface while this architecture is built incrementally.

## UI quality bar

Every new screen should be judged on:

- visual hierarchy
- information density
- action clarity
- responsive behaviour
- empty/loading/error states
- accessibility
- keyboard usability where practical
- consistency with the design tokens
- preservation of existing backend behaviour
