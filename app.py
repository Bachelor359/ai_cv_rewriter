"""
Gradio web UI for AI CV Rewriter.

Run:
    python app.py

The browser opens automatically at http://localhost:7860.
API keys can be entered in the UI — no .env required (but .env values
are used as defaults if present).
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import gradio as gr

from config import (
    CV_META_PATH,
    CV_PATH,
    CV_USER_PATH,
    ANTHROPIC_API_KEY,
    GEMINI_API_KEY,
    OPENAI_API_KEY,
)
from stages.extract import extract_cv_structure
from stages.format import format_cv
from stages.rewrite import rewrite_cv
from token_counter import token_counter


# ---------------------------------------------------------------------------
# Provider / model catalogue
# ---------------------------------------------------------------------------

PROVIDER_MODELS: dict[str, list[str]] = {
    "openai":    ["gpt-4o", "gpt-4o-mini", "o3-mini", "o4-mini", "o1"],
    "anthropic": ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5-20251001"],
    "gemini":    ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
}

_DEFAULT_KEYS: dict[str, str] = {
    "openai":    OPENAI_API_KEY,
    "anthropic": ANTHROPIC_API_KEY,
    "gemini":    GEMINI_API_KEY,
}


# ---------------------------------------------------------------------------
# CV persistence helpers
# ---------------------------------------------------------------------------

def _cv_status_text() -> str:
    """Return the current CV status string (called on page load and after upload)."""
    if CV_USER_PATH.exists() and CV_META_PATH.exists():
        try:
            meta = json.loads(CV_META_PATH.read_text(encoding="utf-8"))
            uploaded_at = meta.get("uploaded_at", "unknown date")
            return f"Your CV was uploaded on {uploaded_at}"
        except Exception:
            return "Your CV was uploaded (metadata unreadable)"
    elif CV_USER_PATH.exists():
        return "Your CV was uploaded (no date recorded)"
    return "No CV uploaded yet — using template"


def _default_api_key(provider: str) -> str:
    """Return the .env API key for the given provider (may be empty string)."""
    return _DEFAULT_KEYS.get(provider, "")


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

def handle_cv_upload(file_obj) -> str:
    """Save uploaded .docx to cv_user.docx and record the upload timestamp."""
    if file_obj is None:
        return _cv_status_text()

    src = Path(file_obj)
    if src.suffix.lower() != ".docx":
        return "ERROR: Please upload a .docx file"

    shutil.copy2(src, CV_USER_PATH)
    uploaded_at = datetime.now().strftime("%d-%m-%Y %H:%M")
    CV_META_PATH.write_text(
        json.dumps({"uploaded_at": uploaded_at}, ensure_ascii=False),
        encoding="utf-8",
    )
    return f"Your CV was uploaded on {uploaded_at}"


def update_model_choices(provider: str):
    choices = PROVIDER_MODELS.get(provider, [])
    return gr.update(choices=choices, value=choices[0] if choices else "")


def update_api_key_default(provider: str):
    return gr.update(value=_default_api_key(provider))


def handle_generate(
    jd_file,
    jd_text: str,
    company: str,
    provider: str,
    api_key: str,
    model: str,
):
    """
    Run the full extract -> rewrite -> format pipeline.

    Returns (status, output_file_path, None, "") where the last two values
    clear the JD file input and JD text area after a successful run.
    """
    # --- Resolve JD (file takes priority) ------------------------------------
    resolved_jd = ""
    if jd_file is not None:
        try:
            resolved_jd = Path(jd_file).read_text(encoding="utf-8")
        except Exception as exc:
            return f"ERROR reading JD file: {exc}", None, jd_file, jd_text

    if not resolved_jd.strip():
        resolved_jd = jd_text.strip()

    if not resolved_jd:
        return "ERROR: Please provide a job description (upload a file or paste text)", None, jd_file, jd_text

    # --- Validate inputs -----------------------------------------------------
    company = company.strip()
    if not company:
        return "ERROR: Please enter a company name", None, jd_file, jd_text

    if not api_key.strip():
        return "ERROR: Please enter your API key", None, jd_file, jd_text

    # --- Resolve CV source ---------------------------------------------------
    cv_source = CV_USER_PATH if CV_USER_PATH.exists() else CV_PATH
    if not cv_source.exists():
        return (
            "ERROR: No CV found. Upload your CV or place cv.docx in the input/ folder",
            None, jd_file, jd_text,
        )

    # --- Run pipeline --------------------------------------------------------
    token_counter.reset()
    try:
        print(f"\n[app] Starting pipeline for company='{company}', provider={provider}/{model}")
        structure = extract_cv_structure(cv_source)
        result = rewrite_cv(
            structure, resolved_jd, company,
            provider=provider,
            api_key=api_key.strip(),
            model=model,
        )
        output_path = format_cv(structure, result, company, cv_source=cv_source)
    except Exception as exc:
        return f"ERROR: {exc}", None, jd_file, jd_text

    # --- Build status message ------------------------------------------------
    status = (
        f"Done. {len(result.slots)} slots rewritten. "
        f"Tokens: {token_counter.total_tokens:,} "
        f"(prompt {token_counter.prompt_tokens:,} / "
        f"completion {token_counter.completion_tokens:,})"
    )
    token_counter.report()  # also print full breakdown to terminal

    # Return: status, output file path, None clears jd_file, "" clears jd_text
    return status, str(output_path), None, ""


# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------

_DEFAULT_PROVIDER = "openai"

with gr.Blocks(title="AI CV Rewriter") as demo:
    gr.Markdown("## AI CV Rewriter")

    # ---- CV section ---------------------------------------------------------
    gr.Markdown("### Your CV")
    with gr.Row():
        with gr.Column(scale=2):
            cv_upload = gr.File(
                label="Upload your CV (.docx)",
                file_types=[".docx"],
                type="filepath",
            )
            cv_template_dl = gr.File(
                label="Download CV template",
                value=str(CV_PATH) if CV_PATH.exists() else None,
                interactive=False,
            )
        with gr.Column(scale=3):
            cv_status = gr.Textbox(
                label="CV status",
                value=_cv_status_text,   # callable — evaluated fresh on each page load
                interactive=False,
                lines=2,
            )

    cv_upload.change(
        fn=handle_cv_upload,
        inputs=[cv_upload],
        outputs=[cv_status],
    )

    gr.Markdown("---")

    # ---- LLM settings -------------------------------------------------------
    gr.Markdown("### AI Settings")
    with gr.Row():
        provider_dd = gr.Dropdown(
            label="Provider",
            choices=list(PROVIDER_MODELS.keys()),
            value=_DEFAULT_PROVIDER,
            scale=1,
        )
        model_dd = gr.Dropdown(
            label="Model",
            choices=PROVIDER_MODELS[_DEFAULT_PROVIDER],
            value=PROVIDER_MODELS[_DEFAULT_PROVIDER][0],
            scale=1,
        )
        api_key_box = gr.Textbox(
            label="API Key",
            placeholder="sk-...",
            value=_default_api_key(_DEFAULT_PROVIDER),
            type="password",
            scale=3,
        )

    provider_dd.change(fn=update_model_choices,    inputs=[provider_dd], outputs=[model_dd])
    provider_dd.change(fn=update_api_key_default,  inputs=[provider_dd], outputs=[api_key_box])

    gr.Markdown("---")

    # ---- Job description ----------------------------------------------------
    gr.Markdown("### Job Description")
    with gr.Row():
        with gr.Column():
            jd_file = gr.File(
                label="Upload .txt file",
                file_types=[".txt"],
                type="filepath",
            )
        with gr.Column():
            jd_text = gr.Textbox(
                label="Or paste text here",
                placeholder="Paste the full job description...",
                lines=10,
            )
    gr.Markdown("*File takes priority if both are provided.*")

    # ---- Company + Generate -------------------------------------------------
    with gr.Row():
        company_box = gr.Textbox(
            label="Company name",
            placeholder="e.g. google",
            scale=3,
        )
        generate_btn = gr.Button("Generate CV", variant="primary", scale=1)

    # ---- Output -------------------------------------------------------------
    status_box = gr.Textbox(label="Status", interactive=False, lines=2)
    output_file = gr.File(label="Download generated CV", interactive=False)

    generate_btn.click(
        fn=handle_generate,
        inputs=[jd_file, jd_text, company_box, provider_dd, api_key_box, model_dd],
        outputs=[status_box, output_file, jd_file, jd_text],
    )


if __name__ == "__main__":
    demo.launch(inbrowser=True)
