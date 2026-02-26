# AI CV Rewriter

Automatically rewrites your CV for each job description to maximise ATS keyword scores and LLM-based candidate screening — while preserving your original template formatting (fonts, sizes, bullet styles, layout).

---

## How it works

1. **Extract** — reads your `cv.docx` and maps every paragraph to a numbered slot
2. **Rewrite** — sends the slots + job description to the configured LLM; the model returns only the slots it wants to change
3. **Format** — writes the rewritten text back into a copy of the original DOCX, slot by slot, keeping all formatting intact

Each stage is independently runnable for debugging or recovery.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure your provider and API key

Copy the example and fill in your credentials:

```bash
cp .env.example .env
```

Then open `.env`:

```
# Choose your LLM provider: openai | anthropic | gemini
LLM_PROVIDER=openai

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Anthropic (Claude) — used when LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-6

# Google Gemini — used when LLM_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-1.5-pro
```

Only the credentials for the active provider need to be filled in.

### 3. Place your CV

Copy your CV template to:

```
input/cv.docx
```

This file is the single source of truth — it is **never modified**.

### 4. Add job descriptions

Create one `.txt` file per company in `input/jobs/`.
The filename (without `.txt`) becomes the company name in the output.

```
input/jobs/google.txt
input/jobs/stripe.txt
input/jobs/yuno.txt
```

---

## Usage

### Full pipeline — all job descriptions at once

```bash
python main.py run
```

Produces one rewritten CV per JD file:

```
output/cv_google.docx
output/cv_stripe.docx
output/cv_yuno.docx
```

Token usage and estimated cost are printed at the end.

### Full pipeline — single job description

```bash
python main.py run --jd input/jobs/google.txt
```

---

## Running stages individually

### Stage 1 — Extract CV structure

```bash
python main.py extract
```

Reads `input/cv.docx`, saves `tmp/cv_structure.json`, and prints a slot preview.
**Re-run this any time you edit `cv.docx`** — the structure must stay in sync.

### Stage 2 — LLM rewrite

```bash
python main.py rewrite --jd input/jobs/google.txt
```

Reads `tmp/cv_structure.json` + the JD, calls the LLM, saves raw output to `tmp/google_{datetime}_raw.json`.

### Stage 3 — Format (apply rewrite to DOCX)

```bash
python main.py format --raw tmp/google_20260226_143022_raw.json
```

Reads `tmp/cv_structure.json` + the raw JSON, writes `output/cv_google.docx`.
**No API call is made** — this is the recovery path when formatting fails after a successful rewrite.

---

## Recovery after a failure

If Stage 3 fails, or you want to re-format without spending tokens again:

```bash
# See what raw JSON files are available
ls tmp/

# Re-run formatting only
python main.py format --raw tmp/google_20260226_143022_raw.json
```

---

## Switching LLM providers

Change one line in `.env` — no code changes needed:

```
LLM_PROVIDER=anthropic   # or: openai | gemini
```

Each provider gets JSON output in a compatible way:

| Provider | JSON mechanism |
|---|---|
| OpenAI (gpt-4o, gpt-4.5, etc.) | `response_format=json_object` |
| OpenAI reasoning (o1, o3, o4-mini) | JSON enforced via prompt only |
| Anthropic (Claude) | Assistant prefill with `{` |
| Google Gemini | `response_mime_type=application/json` |

---

## Project structure

```
ai_cv_rewriter/
├── main.py                  — CLI entry point
├── config.py                — paths, provider selection, API settings
├── llm.py                   — LLM provider abstraction (OpenAI / Anthropic / Gemini)
├── models.py                — data models (CVSlot, CVStructure, RewriteResult)
├── prompts.py               — system prompt and user prompt builder
├── token_counter.py         — accumulates and reports token usage + cost estimate
├── stages/
│   ├── extract.py           — Stage 1: DOCX -> slot JSON
│   ├── rewrite.py           — Stage 2: slot JSON + JD -> rewritten slots (LLM)
│   └── format.py            — Stage 3: rewritten slots -> output DOCX
├── input/
│   ├── cv.docx              — your original CV (place it here)
│   └── jobs/                — job description .txt files
├── output/                  — generated CVs appear here
└── tmp/                     — cv_structure.json + raw LLM output backups
```

---

## What is and isn't changed

| Element | Behaviour |
|---|---|
| Employer names, job titles, dates | **Never changed** (hard rule in the prompt) |
| Contact information | **Never changed** |
| Professional summary | Fully rewritten for the JD |
| Responsibility bullet points | Keyword-injected and clarified |
| Skills / technologies section | Fully rewritten for the JD |
| Fonts, sizes, colours | Preserved from the original template |
| Bullet symbols, indentation | Preserved from the original template |
| Images, logos, decorative shapes | Untouched |

---

## Notes

- **Re-run extract** any time you edit `cv.docx` — the cached slot structure in `tmp/` must match the current file.
- **Multiple runs** for the same company create new timestamped raw files in `tmp/` but overwrite the output DOCX.
- **Cost estimate** is printed after every run based on the active model. Typical cost with `gpt-4o`: ~$0.01–0.03 per JD.
- **Reasoning models** (o1, o3, o4-mini) produce no better prose than gpt-4o for this task and are significantly more expensive. Recommended model: `gpt-4o`.
