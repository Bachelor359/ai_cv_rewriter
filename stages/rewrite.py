"""
Stage 2 – Call the configured LLM provider to rewrite CV slots for a given
job description.

Input:  CVStructure (from Stage 1) + job description text
Output: RewriteResult  (saved to tmp/{company}_{datetime}_raw.json)

Safety measures:
  - Slot-ID validation: any ID the LLM invents that doesn't exist is dropped
  - Retry once on any API or JSON parse error
  - Raw API response always saved to tmp/ before any processing

Run standalone:
  python stages/rewrite.py --jd input/jobs/google.txt [--company google]
  python stages/rewrite.py --jd input/jobs/google.txt --structure tmp/cv_structure.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import llm
from config import TMP_DIR
from models import CVStructure, RewriteResult
from prompts import SYSTEM_PROMPT, build_user_prompt
from token_counter import token_counter


def rewrite_cv(
    structure: CVStructure,
    jd_text: str,
    company: str,
    *,
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> RewriteResult:
    user_prompt = build_user_prompt(structure, jd_text)

    print(f"  [rewrite] Sending {len(structure.non_empty_slots())} non-empty slots"
          f" via {_provider_label(provider, model)}...")

    response, raw_content = _call_with_retry(
        SYSTEM_PROMPT, user_prompt,
        provider=provider, api_key=api_key, model=model,
    )
    token_counter.add(response)

    # --- Parse ---------------------------------------------------------------
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        print(f"  [rewrite] WARNING: JSON parse failed ({exc}). Saving raw and aborting.")
        _save_raw(company, raw_content, {})
        raise

    # Model may return {"slots": {...}} or directly {slot_id: text}
    raw_slots: dict = parsed.get("slots", parsed)
    if not isinstance(raw_slots, dict):
        raise ValueError(f"Unexpected LLM response shape: {type(raw_slots)}")

    # --- Validate slot IDs ---------------------------------------------------
    valid_ids = {str(s.slot_id) for s in structure.slots}
    filtered: dict[str, str] = {}
    skipped = []
    for k, v in raw_slots.items():
        if str(k) in valid_ids:
            filtered[str(k)] = str(v)
        else:
            skipped.append(k)

    if skipped:
        print(f"  [rewrite] Dropped {len(skipped)} unknown slot IDs: {skipped[:5]}")

    print(f"  [rewrite] {len(filtered)} slots rewritten")

    raw_json_path = _save_raw(company, raw_content, filtered)

    return RewriteResult(
        company=company,
        timestamp=_ts(),
        slots=filtered,
        raw_json_path=str(raw_json_path),
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _call_with_retry(
    system: str,
    user: str,
    retries: int = 1,
    *,
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[llm.LLMResponse, str]:
    for attempt in range(retries + 1):
        try:
            response = llm.complete(
                system, user,
                provider=provider, api_key=api_key, model=model,
            )
            return response, response.content
        except Exception as exc:
            if attempt < retries:
                print(f"  [rewrite] API error (attempt {attempt + 1}): {exc}. Retrying...")
            else:
                raise


def _provider_label(provider: str | None = None, model: str | None = None) -> str:
    from config import LLM_PROVIDER, OPENAI_MODEL, ANTHROPIC_MODEL, GEMINI_MODEL
    resolved_provider = provider or LLM_PROVIDER
    model_map = {
        "openai":    OPENAI_MODEL,
        "anthropic": ANTHROPIC_MODEL,
        "gemini":    GEMINI_MODEL,
    }
    resolved_model = model or model_map.get(resolved_provider, "?")
    return f"{resolved_provider}/{resolved_model}"


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _save_raw(company: str, raw_content: str, filtered_slots: dict) -> Path:
    ts = _ts()
    path = TMP_DIR / f"{company}_{ts}_raw.json"
    payload = {
        "company": company,
        "timestamp": ts,
        "raw_response": raw_content,
        "slots": filtered_slots,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [rewrite] Raw saved -> {path}")
    return path


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 2: LLM CV rewrite")
    parser.add_argument("--jd", required=True, help="Path to job description .txt file")
    parser.add_argument("--company", help="Company name (default: JD filename stem)")
    parser.add_argument(
        "--structure",
        default=str(TMP_DIR / "cv_structure.json"),
        help="Path to cv_structure.json from Stage 1",
    )
    args = parser.parse_args()

    jd_path = Path(args.jd)
    if not jd_path.exists():
        print(f"[rewrite] JD file not found: {jd_path}")
        sys.exit(1)

    structure_path = Path(args.structure)
    if not structure_path.exists():
        print(f"[rewrite] Structure file not found: {structure_path}")
        print("  Run Stage 1 first:  python main.py extract")
        sys.exit(1)

    company = args.company or jd_path.stem
    structure = CVStructure.model_validate_json(structure_path.read_text(encoding="utf-8"))
    jd_text = jd_path.read_text(encoding="utf-8")

    result = rewrite_cv(structure, jd_text, company)
    print(f"[rewrite] Done. {len(result.slots)} slots rewritten -> {result.raw_json_path}")
    token_counter.report()


if __name__ == "__main__":
    main()
