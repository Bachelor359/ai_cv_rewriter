"""
Stage 3 – Apply rewritten slots back into a copy of the original DOCX.

Algorithm per slot:
  1. Locate the paragraph element using slot.indices + slot.location
  2. Consolidate all <w:r> runs -> single run (preserves first run's character
     formatting: font, size, bold, italic, colour, etc.)
  3. Set the run's text to the rewritten string

Critical design decisions:
  - We always copy the ORIGINAL cv.docx; the source is never modified.
  - Run consolidation is intentionally "destructive" for mid-paragraph inline
    formatting variation, which is acceptable for standard CV templates.
  - Text boxes are resolved via the same XML iteration order used in Stage 1,
    so indices stay stable as long as the document structure hasn't changed.
  - If a slot is missing from the rewrite result, its original text is kept.

Run standalone (recovery from a saved raw JSON):
  python stages/format.py --raw tmp/google_20240101_120000_raw.json
  python stages/format.py --raw tmp/... --structure tmp/cv_structure.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from lxml import etree

from config import CV_PATH, OUTPUT_DIR, TMP_DIR
from models import CVSlot, CVStructure, RewriteResult, SlotLocation


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def format_cv(
    structure: CVStructure,
    result: RewriteResult,
    company: str,
) -> Path:
    """
    Write a new DOCX to output/cv_{company}.docx with rewritten slot text.
    Returns the output path.
    """
    output_path = OUTPUT_DIR / f"cv_{company}.docx"
    shutil.copy2(CV_PATH, output_path)

    doc = Document(str(output_path))

    # Normalise keys to int for fast lookup
    rewritten: dict[int, str] = {int(k): v for k, v in result.slots.items()}

    # Pre-compute textbox elements once (same order as Stage 1)
    textboxes = list(doc.element.body.iter(qn("w:txbxContent")))

    changed = 0
    for slot in structure.slots:
        para = _resolve_slot(doc, slot, textboxes)
        if para is None:
            print(f"  [format] WARNING: could not resolve slot {slot.slot_id} — skipping")
            continue

        if slot.merged_into is None:
            # Primary slot: write the rewritten text (or skip if LLM didn't touch it)
            if slot.slot_id not in rewritten:
                continue
            _set_paragraph_text(para, rewritten[slot.slot_id])
            changed += 1
        else:
            # Continuation slot: blank it out if its primary was rewritten.
            # The full merged text was already written to the primary paragraph.
            if slot.merged_into in rewritten:
                _set_paragraph_text(para, "")

    doc.save(str(output_path))
    print(f"  [format] {changed} primary slots applied -> {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Slot resolution — find the paragraph object for a given slot
# ---------------------------------------------------------------------------

def _resolve_slot(
    doc: Document,
    slot: CVSlot,
    textboxes: list,
) -> Paragraph | None:
    idx = slot.indices
    try:
        if slot.location == SlotLocation.BODY:
            return doc.paragraphs[idx[0]]

        elif slot.location == SlotLocation.TABLE:
            table_idx, row_idx, col_idx, para_idx = idx
            table = doc.tables[table_idx]
            # Resolve col_idx accounting for merged-cell deduplication done in Stage 1.
            # We walk the cells the same way (skipping duplicate _tc elements).
            unique_cells = _unique_cells(table.rows[row_idx])
            cell = unique_cells[col_idx]
            return cell.paragraphs[para_idx]

        elif slot.location == SlotLocation.HEADER:
            section_idx, para_idx = idx
            return doc.sections[section_idx].header.paragraphs[para_idx]

        elif slot.location == SlotLocation.FOOTER:
            section_idx, para_idx = idx
            return doc.sections[section_idx].footer.paragraphs[para_idx]

        elif slot.location == SlotLocation.TEXTBOX:
            tb_idx, para_idx = idx
            if tb_idx >= len(textboxes):
                return None
            p_elems = textboxes[tb_idx].findall(f".//{qn('w:p')}")
            if para_idx >= len(p_elems):
                return None
            # Wrap raw XML element in a Paragraph object.
            # The parent arg is only used for add_run() calls, which we don't need.
            return Paragraph(p_elems[para_idx], None)

    except (IndexError, TypeError, AttributeError) as exc:
        print(f"  [format] WARNING: slot {slot.slot_id} resolve error: {exc}")
        return None

    return None


def _unique_cells(row) -> list:
    """Return deduplicated cell list for a row (same logic as Stage 1)."""
    seen: set[int] = set()
    cells = []
    for cell in row.cells:
        eid = id(cell._tc)
        if eid not in seen:
            seen.add(eid)
            cells.append(cell)
    return cells


# ---------------------------------------------------------------------------
# Text replacement with run consolidation
# ---------------------------------------------------------------------------

def _first_text_run_idx(runs: list) -> int:
    """
    Return the index of the first run that contains non-whitespace text.
    Falls back to 0 if every run is whitespace-only or empty (e.g. all <w:sym>).
    """
    for i, run in enumerate(runs):
        if run.text and run.text.strip():
            return i
    return 0


def _set_paragraph_text(para: Paragraph, new_text: str) -> None:
    """
    Replace paragraph content with new_text, preserving the character
    formatting of the FIRST TEXT-BEARING run (not a symbol/bullet marker run).

    CV templates often start a bullet paragraph with a <w:sym> run (the bullet
    character in a special font, e.g. Wingdings) followed by a tab run and
    then the actual text run.  If we blindly use runs[0] we inherit the
    bullet's large/bold formatting for ALL the text, and we may also produce a
    double-dot if the <w:sym> element survives the run.text assignment.

    Strategy:
      1. Find the first run that contains real non-whitespace text.
      2. Use THAT run's character formatting as the base.
      3. Keep every run that precedes it untouched (preserves bullet symbol,
         tab spacing, etc.).
      4. Remove every run that follows it (they are continuations of the same
         text that we are replacing wholesale).
    """
    # python-docx Paragraph.runs returns only direct <w:r> children.
    # This excludes runs inside revision marks (<w:ins>/<w:del>).
    # For normal CVs without tracked changes this is fine.
    runs = para.runs

    if not runs:
        # Paragraph has no runs (e.g. empty paragraph or special element).
        # Just add a run — it will inherit the paragraph style.
        para.add_run(new_text)
        return

    # Find the first run with actual (non-whitespace) text content.
    # Runs before it (bullet symbols, tabs) are left untouched.
    target_idx = _first_text_run_idx(runs)
    target_run = runs[target_idx]
    target_run.text = new_text  # python-docx handles xml:space="preserve"

    # Remove all runs that follow the target (text continuation runs).
    for run in runs[target_idx + 1:]:
        run._element.getparent().remove(run._element)


# ---------------------------------------------------------------------------
# CLI entry-point (recovery path: format from a saved raw JSON)
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 3: Format DOCX from rewrite result")
    parser.add_argument("--raw", required=True, help="Path to *_raw.json file from Stage 2")
    parser.add_argument(
        "--structure",
        default=str(TMP_DIR / "cv_structure.json"),
        help="Path to cv_structure.json from Stage 1",
    )
    args = parser.parse_args()

    raw_path = Path(args.raw)
    structure_path = Path(args.structure)

    if not raw_path.exists():
        print(f"[format] Raw JSON not found: {raw_path}")
        sys.exit(1)
    if not structure_path.exists():
        print(f"[format] Structure file not found: {structure_path}")
        print("  Run Stage 1 first:  python stages/extract.py")
        sys.exit(1)
    if not CV_PATH.exists():
        print(f"[format] Original CV not found: {CV_PATH}")
        sys.exit(1)

    structure = CVStructure.model_validate_json(structure_path.read_text(encoding="utf-8"))

    raw_data = json.loads(raw_path.read_text(encoding="utf-8"))
    result = RewriteResult(
        company=raw_data["company"],
        timestamp=raw_data.get("timestamp", ""),
        slots=raw_data["slots"],
        raw_json_path=str(raw_path),
    )

    output = format_cv(structure, result, result.company)
    print(f"[format] Done -> {output}")


if __name__ == "__main__":
    main()
