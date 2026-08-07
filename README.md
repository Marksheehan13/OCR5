# OCR5: LLM-Based Invoice Extraction

Successor to [OCR4](https://github.com/Marksheehan13/OCR4). Same
purpose (extract date, supplier, and total amount from photographed
invoices into Excel), same review UI, but a fundamentally different
extraction approach: instead of OCR + hand-written scoring rules,
invoice images are sent directly to Claude, which reads and extracts
the fields with its own confidence and reasoning.

**See [`docs/comparison.md`](docs/comparison.md) for the full
rationale** on why this rebuild happened -- OCR4's rule-based scoring
hit a real, benchmarked accuracy ceiling (it kept confusing a
cashier's name for the store name), and no amount of additional
heuristic patching was going to categorically fix that.

## Features

- **Understands, not just pattern-matches** -- Claude reads each
  invoice the way a person would, rather than scoring keyword
  proximity and letter case.
- **Simple, fast pipeline** -- one API call per invoice, no local OCR
  passes, no preprocessing stack.
- **Confidence + reasoning per field** -- the model reports its own
  certainty and explains why, surfaced in the UI via a "Why?" popover
  on each field.
- **Excel export** with confidence-based highlighting (same format as
  OCR4).
- **Streamlit web UI** with manual review/edit before export.

## Setup

```bash
git clone https://github.com/Marksheehan13/OCR5.git
cd OCR5
pip install -r requirements.txt
```

You'll need an Anthropic API key (console.anthropic.com):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

**CLI:**

```bash
python main.py --input ./sample_data/invoices --output invoices.xlsx
```

**Web UI:**

```bash
streamlit run app.py
```

If no `ANTHROPIC_API_KEY` environment variable is set, the app's
sidebar will prompt for one to paste in directly (useful for local
testing without exporting an env var).

## Testing

```bash
pytest tests/ -v
```

The test suite mocks the Anthropic API entirely -- it runs free,
offline, and fast, and tests the parsing/orchestration logic (does
OCR5 correctly handle what the API gives it), not "is Claude good at
reading invoices." For that, run it against real images with a real
key and check the results by eye, or point it at a labeled dataset
like [ICDAR-SROIE](https://github.com/zzzDavid/ICDAR-2019-SROIE) the
same way OCR4's `tests/benchmark.py` does.

## Deployment (Streamlit Cloud)

1. Push this repo to GitHub.
2. Deploy at [share.streamlit.io](https://share.streamlit.io), main
   file `app.py`.
3. In the app's **Settings -> Secrets**, add:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
No `packages.txt` needed this time -- there's no Tesseract/OpenCV
dependency anymore, so none of OCR4's apt-package deployment issues
apply here.

## Project structure

```
OCR5/
├── app.py                  Streamlit web UI
├── main.py                 CLI entry point
├── requirements.txt
├── README.md
├── src/
│   ├── llm_extractor.py     sends the image to Claude, parses the response
│   ├── excel_writer.py      formatted .xlsx export (unchanged from OCR4)
│   └── models.py            shared dataclasses
├── tests/
│   ├── test_llm_extractor.py  mocked-API tests for parsing/orchestration
│   └── test_excel_writer.py
├── sample_data/
│   ├── invoices/             sample invoice images (shared with OCR4)
│   └── expected_results.json
└── docs/
    └── comparison.md         why OCR5 exists, honest tradeoffs vs OCR4
```

## Future improvements

- **Batch/prompt caching** to reduce cost when processing many
  invoices from the same vendor repeatedly.
- **Structured output validation** (e.g. Pydantic schema enforcement)
  as an extra safety net beyond the JSON-parsing in `llm_extractor.py`.
- **Persistent storage** -- same as noted in OCR4's README, a database
  of processed invoices instead of stateless per-session exports.
- **Hybrid fallback**: try a cheap/fast path first and only call the
  LLM for genuinely ambiguous cases, if cost at scale becomes a
  concern.
