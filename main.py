"""
main.py

Command-line entry point for OCR5. Same interface as OCR4's main.py --
processes every supported image in a folder (or a single file) and
writes an Excel report -- but extraction is now one Claude API call
per image instead of 16 local OCR passes.

Requires the ANTHROPIC_API_KEY environment variable to be set.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python main.py --input ./invoices --output results.xlsx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.excel_writer import write_invoices_to_excel
from src.llm_extractor import ExtractionError, extract_invoice

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".bmp", ".tiff", ".webp"}


def _collect_image_paths(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    return sorted(
        p for p in input_path.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR5: LLM-based invoice extraction")
    parser.add_argument("--input", required=True, help="Path to an image file or a folder of images")
    parser.add_argument("--output", default="invoices.xlsx", help="Path to the output .xlsx file")
    parser.add_argument("--model", default="claude-sonnet-5", help="Claude model to use")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input path '{input_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    image_paths = _collect_image_paths(input_path)
    if not image_paths:
        print(f"No supported images found in '{input_path}'.", file=sys.stderr)
        sys.exit(1)

    results = []
    for path in image_paths:
        print(f"Processing {path.name} ...")
        try:
            result = extract_invoice(str(path), model=args.model)
        except ExtractionError as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            continue

        status = "REVIEW" if result.needs_review else "OK"
        print(
            f"  [{status}] date={result.date.value} supplier={result.supplier.value} "
            f"amount={result.amount.value} confidence={result.overall_confidence}%"
        )
        results.append(result)

    write_invoices_to_excel(results, args.output)
    print(f"\nWrote {len(results)} invoice(s) to {args.output}")


if __name__ == "__main__":
    main()
