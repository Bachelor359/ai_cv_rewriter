"""
Build script: creates a clean standalone distribution for end users.

Usage (developer only — run once per release):
    python build.py

What users receive (cv_rewriter.zip):
    cv_rewriter/
    ├── cv_rewriter.exe     <- double-click to run (browser opens automatically)
    ├── README.txt          <- quick-start instructions
    ├── input/
    │   └── cv.docx         <- downloadable CV template
    └── output/             <- generated CVs appear here (created on first run)

Everything else (Python runtime, packages) is bundled inside the .exe itself.
First launch takes ~15s to unpack; subsequent launches are similar (onefile mode).
"""

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).parent
DIST_EXE = HERE / "dist" / "cv_rewriter.exe"   # onefile output
DIST_PACKAGE = HERE / "dist" / "cv_rewriter"   # final folder we zip

README_TEXT = """\
AI CV Rewriter
==============

1. Double-click cv_rewriter.exe
   (First launch takes ~15 seconds — the app is unpacking itself. Wait for
   the browser to open automatically at http://localhost:7860)

2. In the browser:
   - Upload your CV (.docx) once — it will be remembered next time
   - Choose your AI provider and paste your API key
   - Upload or paste a job description
   - Enter the company name and click Generate CV
   - Download the tailored CV from the result section

3. Find generated CVs in the output/ folder next to this file.

CV Template
-----------
A blank CV template is available for download directly from the app UI.

Supported AI providers
-----------------------
  OpenAI   : https://platform.openai.com/api-keys
  Anthropic: https://console.anthropic.com/settings/keys
  Gemini   : https://aistudio.google.com/app/apikey
"""

# ---------------------------------------------------------------------------
# PyInstaller command — --onefile bundles everything into a single exe
# ---------------------------------------------------------------------------

cmd = [
    sys.executable, "-m", "PyInstaller",
    "app.py",
    "--name", "cv_rewriter",
    "--onefile",         # single exe — clean distribution, ~15s first-launch unpack
    "--noconfirm",       # overwrite previous build without asking
    # Collect entire packages (Python files + data files + binaries)
    "--collect-all", "gradio",
    "--collect-all", "gradio_client",
    "--collect-all", "lxml",
    "--collect-all", "tiktoken",
    "--collect-all", "google.generativeai",
    "--collect-all", "google.protobuf",
    "--collect-all", "openai",
    "--collect-all", "anthropic",
    "--collect-all", "docx",         # python-docx internal templates
    # Hidden imports PyInstaller sometimes misses
    "--hidden-import", "pydantic",
    "--hidden-import", "pydantic.v1",
    "--hidden-import", "pydantic_core",
    "--hidden-import", "lxml.etree",
    "--hidden-import", "lxml._elementpath",
    "--hidden-import", "uvicorn.logging",
    "--hidden-import", "uvicorn.loops",
    "--hidden-import", "uvicorn.loops.auto",
    "--hidden-import", "uvicorn.protocols",
    "--hidden-import", "uvicorn.protocols.http",
    "--hidden-import", "uvicorn.protocols.http.auto",
    "--hidden-import", "uvicorn.protocols.websockets",
    "--hidden-import", "uvicorn.protocols.websockets.auto",
    "--hidden-import", "uvicorn.lifespan",
    "--hidden-import", "uvicorn.lifespan.on",
    "--hidden-import", "python_multipart",
]

print("Running PyInstaller (this takes a few minutes)...")
subprocess.run(cmd, check=True)

# ---------------------------------------------------------------------------
# Assemble the clean distribution folder
# ---------------------------------------------------------------------------

if DIST_PACKAGE.exists():
    shutil.rmtree(DIST_PACKAGE)
DIST_PACKAGE.mkdir(parents=True)

# exe
shutil.copy2(DIST_EXE, DIST_PACKAGE / "cv_rewriter.exe")

# README
(DIST_PACKAGE / "README.txt").write_text(README_TEXT, encoding="utf-8")

# CV template
dist_input = DIST_PACKAGE / "input"
dist_input.mkdir()
cv_template = HERE / "input" / "cv.docx"
if cv_template.exists():
    shutil.copy2(cv_template, dist_input / "cv.docx")
    print(f"Copied CV template -> {dist_input / 'cv.docx'}")
else:
    print("WARNING: input/cv.docx not found — users won't have a downloadable template")

# output/ placeholder so the folder is visible in the zip
(DIST_PACKAGE / "output" / ".keep").write_text("Generated CVs appear here.\n")

# ---------------------------------------------------------------------------
# Zip it up
# ---------------------------------------------------------------------------

zip_path = HERE / "dist" / "cv_rewriter.zip"
print(f"\nCreating {zip_path} ...")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
    for file in DIST_PACKAGE.rglob("*"):
        if file.is_file():
            zf.write(file, file.relative_to(DIST_PACKAGE.parent))

print(f"\nDone! Distribute: {zip_path}")
print("\nUsers see inside the zip:")
print("  cv_rewriter/")
print("  ├── cv_rewriter.exe")
print("  ├── README.txt")
print("  ├── input/cv.docx")
print("  └── output/")
