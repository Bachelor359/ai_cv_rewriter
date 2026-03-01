"""
LLM provider abstraction.

All three providers expose the same interface:
    response = complete(system_prompt, user_prompt)
    response.content          # str — the model's reply
    response.prompt_tokens    # int
    response.completion_tokens  # int
    response.total_tokens     # int (property)

Set LLM_PROVIDER in .env to switch:  openai | anthropic | gemini
"""

from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Unified response type
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def complete(
    system: str,
    user: str,
    *,
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> LLMResponse:
    """Route to the configured LLM provider and return a normalised response.

    provider/api_key/model override .env config when supplied (used by Gradio UI).
    Omit them (or pass None) to fall back to config — CLI behaviour unchanged.
    """
    from config import LLM_PROVIDER
    resolved_provider = provider or LLM_PROVIDER
    providers = {
        "openai":    _openai_complete,
        "anthropic": _anthropic_complete,
        "gemini":    _gemini_complete,
    }
    if resolved_provider not in providers:
        raise ValueError(
            f"Unknown LLM provider: '{resolved_provider}'. "
            f"Valid options: {', '.join(providers)}"
        )
    return providers[resolved_provider](system, user, api_key=api_key, model=model)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

# Reasoning models use a different API surface:
#   - No `temperature` parameter (they use internal chain-of-thought)
#   - No `response_format` (o1 series); o3/o4 support it but we keep it simple
#   - Use `max_completion_tokens` instead of `max_tokens`
_OPENAI_REASONING_PREFIXES = ("o1", "o3", "o4")


def _is_reasoning_model(model: str) -> bool:
    return any(model == p or model.startswith(p + "-") for p in _OPENAI_REASONING_PREFIXES)


def _openai_complete(
    system: str,
    user: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> LLMResponse:
    from openai import OpenAI
    from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_TEMPERATURE

    resolved_key   = api_key or OPENAI_API_KEY
    resolved_model = model   or OPENAI_MODEL
    client = OpenAI(api_key=resolved_key)

    if _is_reasoning_model(resolved_model):
        # Reasoning models: no temperature, no response_format.
        # Instruct JSON output via the prompt only (system prompt already does this).
        response = client.chat.completions.create(
            model=resolved_model,
            max_completion_tokens=8192,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
    else:
        response = client.chat.completions.create(
            model=resolved_model,
            temperature=OPENAI_TEMPERATURE,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )

    usage = response.usage
    return LLMResponse(
        content=response.choices[0].message.content or "{}",
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
    )


# ---------------------------------------------------------------------------
# Anthropic (Claude)
# ---------------------------------------------------------------------------

def _anthropic_complete(
    system: str,
    user: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> LLMResponse:
    import anthropic
    from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, OPENAI_TEMPERATURE

    resolved_key   = api_key or ANTHROPIC_API_KEY
    resolved_model = model   or ANTHROPIC_MODEL
    client = anthropic.Anthropic(api_key=resolved_key)

    # Prefill the assistant turn with "{" to force the model to start a JSON
    # object immediately — no preamble, no markdown fences.
    response = client.messages.create(
        model=resolved_model,
        max_tokens=4096,
        temperature=OPENAI_TEMPERATURE,
        system=system,
        messages=[
            {"role": "user",      "content": user},
            {"role": "assistant", "content": "{"},   # JSON prefill
        ],
    )

    # The API returns only the continuation; restore the prefilled "{".
    raw = "{" + (response.content[0].text if response.content else "}")

    return LLMResponse(
        content=raw,
        prompt_tokens=response.usage.input_tokens,
        completion_tokens=response.usage.output_tokens,
    )


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

def _gemini_complete(
    system: str,
    user: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> LLMResponse:
    import google.generativeai as genai
    from config import GEMINI_API_KEY, GEMINI_MODEL, OPENAI_TEMPERATURE

    resolved_key   = api_key or GEMINI_API_KEY
    resolved_model = model   or GEMINI_MODEL
    genai.configure(api_key=resolved_key)
    gmodel = genai.GenerativeModel(
        model_name=resolved_model,
        system_instruction=system,
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
            temperature=OPENAI_TEMPERATURE,
        ),
    )
    response = gmodel.generate_content(user)
    meta = response.usage_metadata

    return LLMResponse(
        content=response.text,
        prompt_tokens=getattr(meta, "prompt_token_count", 0),
        completion_tokens=getattr(meta, "candidates_token_count", 0),
    )
