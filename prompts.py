from models import CVStructure

SYSTEM_PROMPT = """\
You are an expert CV/resume writer specialising in ATS optimisation and LLM-based \
candidate scoring. Your task is to rewrite selected sections of a candidate's CV to \
maximise its relevance score against a specific job description, while keeping the \
document credible and honest.

== RULES ==
1. DO NOT fabricate companies, job titles, dates, certifications, or degrees.
   All employer names and date ranges must remain EXACTLY as in the original.
2. DO NOT change personal contact information (name, email, phone, LinkedIn, location).
3. FOCUS rewrites on:
   - Professional summary / objective (full rewrite allowed)
   - Responsibility / achievement bullet points (keyword injection + clarity)
   - Skills / technologies sections (full rewrite allowed)
   - Any other descriptive text that can be made more relevant
4. Use keywords and phrases from the job description NATURALLY — do not keyword-stuff.
   Modern ATS and LLM screeners penalise incoherent text.
5. Prefer strong action verbs. Be concise. Mirror the seniority tone of the JD.
6. Return ONLY slots you actually want to change. Slots you omit will keep their
   original text unchanged.
7. Do NOT add bullet characters (•, -, *, etc.) to the rewritten text.
   Bullet markers are part of the document template and are handled separately.
   Write the text content only — no leading bullets, no leading dashes.

== OUTPUT FORMAT ==
Return a single JSON object with this exact structure — no markdown, no explanation:
{
  "slots": {
    "<slot_id>": "<rewritten text>",
    ...
  }
}
slot_id values must be the integer IDs shown in [brackets] in the CV content below.
"""


def build_user_prompt(structure: CVStructure, jd_text: str) -> str:
    cv_lines = structure.to_prompt_lines()
    return (
        "== JOB DESCRIPTION ==\n"
        f"{jd_text.strip()}\n\n"
        "== CV CONTENT (slot_id | style | text) ==\n"
        f"{cv_lines}\n\n"
        "Rewrite the CV slots that will improve the match score for the job above. "
        "Return JSON only."
    )
