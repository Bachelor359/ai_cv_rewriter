"""
AI CV Rewriter — CLI orchestrator

Usage
-----
Full pipeline (all JDs in input/jobs/):
  python main.py run

Full pipeline for a single JD:
  python main.py run --jd input/jobs/google.txt

Stage 1 only — extract CV structure:
  python main.py extract

Stage 2 only — LLM rewrite for one JD:
  python main.py rewrite --jd input/jobs/google.txt [--company google]

Stage 3 only — format from a saved raw JSON (recovery path):
  python main.py format --raw tmp/google_20240101_120000_raw.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from config import CV_PATH, JOBS_DIR, TMP_DIR
from models import CVStructure, RewriteResult
from stages.extract import extract_cv_structure
from stages.rewrite import rewrite_cv
from stages.format import format_cv
from token_counter import token_counter


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def cmd_extract(args: argparse.Namespace) -> None:
    _require_cv()
    print("[Stage 1] Extracting CV structure…")
    structure = extract_cv_structure(CV_PATH)

    out_path = TMP_DIR / "cv_structure.json"
    out_path.write_text(structure.model_dump_json(indent=2), encoding="utf-8")

    non_empty = len(structure.non_empty_slots())
    print(f"[Stage 1] {len(structure.slots)} slots total  ({non_empty} non-empty)  -> {out_path}")


def cmd_rewrite(args: argparse.Namespace) -> None:
    jd_path = _require_file(args.jd, "Job description")
    structure_path = _require_structure()

    company = args.company or jd_path.stem
    structure = CVStructure.model_validate_json(structure_path.read_text(encoding="utf-8"))
    jd_text = jd_path.read_text(encoding="utf-8")

    print(f"[Stage 2] Rewriting for: {company}")
    result = rewrite_cv(structure, jd_text, company)
    print(f"[Stage 2] Done -> {result.raw_json_path}")
    token_counter.report()


def cmd_format(args: argparse.Namespace) -> None:
    _require_cv()
    raw_path = _require_file(args.raw, "Raw JSON")
    structure_path = _require_structure()

    structure = CVStructure.model_validate_json(structure_path.read_text(encoding="utf-8"))
    raw_data = json.loads(raw_path.read_text(encoding="utf-8"))
    result = RewriteResult(
        company=raw_data["company"],
        timestamp=raw_data.get("timestamp", ""),
        slots=raw_data["slots"],
        raw_json_path=str(raw_path),
    )

    print(f"[Stage 3] Formatting CV for: {result.company}")
    output = format_cv(structure, result, result.company)
    print(f"[Stage 3] Done -> {output}")


def cmd_run(args: argparse.Namespace) -> None:
    _require_cv()

    # --- Stage 1: extract once ---------------------------------------------
    print("\n[Stage 1] Extracting CV structure…")
    structure = extract_cv_structure(CV_PATH)
    structure_cache = TMP_DIR / "cv_structure.json"
    structure_cache.write_text(structure.model_dump_json(indent=2), encoding="utf-8")
    non_empty = len(structure.non_empty_slots())
    print(f"  {len(structure.slots)} slots  ({non_empty} non-empty)  -> {structure_cache}")

    # --- Collect JD files ---------------------------------------------------
    if hasattr(args, "jd") and args.jd:
        jd_files = [_require_file(args.jd, "Job description")]
    else:
        jd_files = sorted(JOBS_DIR.glob("*.txt"))

    if not jd_files:
        print(f"\nNo .txt files found in {JOBS_DIR}")
        print("Drop your job description files there and re-run.")
        sys.exit(0)

    print(f"\nFound {len(jd_files)} job description(s): {[f.stem for f in jd_files]}")

    # --- Stage 2 + 3 per JD ------------------------------------------------
    results: list[tuple[str, Path]] = []
    errors: list[str] = []

    for jd_path in jd_files:
        company = jd_path.stem
        print(f"\n{'='*50}")
        print(f"  Company: {company}")
        print(f"{'='*50}")

        try:
            print("\n[Stage 2] LLM rewriting…")
            jd_text = jd_path.read_text(encoding="utf-8")
            rewrite_result = rewrite_cv(structure, jd_text, company)

            print("\n[Stage 3] Formatting DOCX…")
            output_path = format_cv(structure, rewrite_result, company)
            results.append((company, output_path))

        except Exception as exc:
            print(f"\n  ERROR for {company}: {exc}")
            errors.append(f"{company}: {exc}")

    # --- Summary ------------------------------------------------------------
    print(f"\n{'='*50}")
    print("  SUMMARY")
    print(f"{'='*50}")
    for company, path in results:
        print(f"  ✓ {company:30} -> {path.name}")
    for err in errors:
        print(f"  ✗ {err}")

    token_counter.report()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cv-rewriter",
        description="AI-powered CV rewriter — ATS & LLM optimisation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # run
    run_p = subparsers.add_parser("run", help="Full pipeline (default)")
    run_p.add_argument("--jd", metavar="FILE", help="Single JD file (default: all in input/jobs/)")

    # extract
    subparsers.add_parser("extract", help="Stage 1 only: extract CV structure to tmp/")

    # rewrite
    rew_p = subparsers.add_parser("rewrite", help="Stage 2 only: LLM rewrite for one JD")
    rew_p.add_argument("--jd", required=True, metavar="FILE", help="Job description .txt file")
    rew_p.add_argument("--company", metavar="NAME", help="Company name (default: JD filename)")

    # format
    fmt_p = subparsers.add_parser("format", help="Stage 3 only: format DOCX from saved raw JSON")
    fmt_p.add_argument("--raw", required=True, metavar="FILE", help="tmp/*_raw.json from Stage 2")

    return parser


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def _require_cv() -> None:
    if not CV_PATH.exists():
        print(f"ERROR: Original CV not found at {CV_PATH}")
        print("Place your cv.docx in the input/ directory.")
        sys.exit(1)


def _require_structure() -> Path:
    path = TMP_DIR / "cv_structure.json"
    if not path.exists():
        print(f"ERROR: Structure file not found at {path}")
        print("Run Stage 1 first:  python main.py extract")
        sys.exit(1)
    return path


def _require_file(filepath: str, label: str) -> Path:
    path = Path(filepath)
    if not path.exists():
        print(f"ERROR: {label} file not found: {path}")
        sys.exit(1)
    return path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Default to "run" when no sub-command given
    if args.command is None:
        args.command = "run"
        args.jd = None  # will pick up all JDs

    dispatch = {
        "run": cmd_run,
        "extract": cmd_extract,
        "rewrite": cmd_rewrite,
        "format": cmd_format,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
