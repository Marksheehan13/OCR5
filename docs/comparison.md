# OCR4 vs OCR5: Why the Rebuild

## The problem with OCR4

OCR4 ([repo](https://github.com/Marksheehan13/OCR4)) is OCR + hand-written
scoring rules: "+10 if the word 'total' is nearby," "+5 if the line is
ALL CAPS," etc. It has no actual understanding of what it's looking
at -- it's pattern-matching dressed up as intelligence.

Benchmarking OCR4 against real receipts (the public
[ICDAR-SROIE dataset](https://github.com/zzzDavid/ICDAR-2019-SROIE))
surfaced this clearly. The most persistent failure: vendor extraction
kept picking a person's name off the receipt (e.g. "tan woon yann," a
registered sole-proprietor's legal name printed above the trading
name) instead of the actual store name ("INDAH GIFT & HOME DECO"). The
fix was a heuristic -- reward ALL-CAPS lines, penalize lowercase ones
-- because store names print in caps and personal names usually don't
on these receipts. That fix worked, but it's a patch for one specific
way the rules got fooled. The next unusual receipt layout will find a
new way. That's the ceiling of a rules-based approach: it can only be
as smart as every case its author thought to handle.

It was also slow: 16 OCR passes (4 image preprocessing variants x 4
Tesseract page-segmentation modes) plus heavy preprocessing
(orientation detection, perspective correction, denoising, deskew)
took 60-90 seconds per invoice on modest hardware.

## What OCR5 does differently

OCR5 sends the invoice image directly to Claude and asks it to read
and extract the fields, with its own confidence and reasoning per
field (`src/llm_extractor.py`). This isn't a bigger patch -- it's a
different kind of system. Claude can tell "this is a person's name"
from "this is a store name" through actual reading comprehension, the
same way a person glancing at the receipt would, rather than through
a letter-case proxy that happens to correlate with the right answer
most of the time.

Practically, this also collapses the pipeline: one API call replaces
sixteen local OCR passes and the entire preprocessing stack (no more
orientation detection, perspective correction, or deskew logic --
Claude reads angled/rotated photos directly). `src/llm_extractor.py`
is ~150 lines; OCR4's equivalent (`preprocess.py` + `ocr_engine.py` +
`invoice_parser.py` + `confidence.py`) is roughly 700.

## Honest tradeoffs

| | OCR4 | OCR5 |
|---|---|---|
| Cost per invoice | Free (local compute only) | Small API cost |
| Requires | Nothing (fully offline) | An Anthropic API key |
| Speed | 60-90s/invoice | Single API round-trip (seconds) |
| Handles novel layouts | Only as well as the rules anticipate | Generalizes via actual language/vision understanding |
| Explainability | Rule-level ("+10 for keyword X") | Model's own stated reasoning per field |
| Offline / air-gapped use | Yes | No -- needs network + API access |

Neither is strictly "better" -- OCR4 is the right call if you need
zero-cost, fully offline, air-gapped processing and can tolerate lower
accuracy on unusual layouts. OCR5 is the right call if accuracy on
real-world, varied invoices matters more than infrastructure
constraints.

## What's identical between the two

`excel_writer.py` (export format + confidence highlighting) and the
Streamlit UI's review/edit/approve workflow are unchanged between
OCR4 and OCR5 -- only the extraction layer underneath was replaced.
This was deliberate: the parts that worked stayed, only the part that
had hit a real ceiling was rebuilt.
