import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# When frozen by PyInstaller, use the exe's directory so that output/, tmp/,
# and input/ are created next to the executable (not inside the temp bundle).
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "input"
JOBS_DIR = INPUT_DIR / "jobs"
OUTPUT_DIR = BASE_DIR / "output"
TMP_DIR = BASE_DIR / "tmp"
CV_PATH = INPUT_DIR / "cv.docx"
CV_USER_PATH = INPUT_DIR / "cv_user.docx"   # user's personal CV (gitignored)
CV_META_PATH = INPUT_DIR / "cv_meta.json"   # upload timestamp metadata (gitignored)

# --- LLM provider selection ------------------------------------------------
# Valid values: openai | anthropic | gemini
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")

# Shared
OPENAI_TEMPERATURE: float = 0.3

# OpenAI
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

# Anthropic (Claude)
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

# Google Gemini
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")

# Ensure runtime dirs exist
for _d in [OUTPUT_DIR, TMP_DIR, JOBS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)
