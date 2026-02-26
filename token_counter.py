from dataclasses import dataclass, field

# Rough pricing per 1M tokens (prompt, completion) as of early 2026.
# Update these when provider pricing changes.
_COST_RATES: dict[str, tuple[float, float]] = {
    # OpenAI — standard chat models
    "gpt-4o":                    (2.50,  10.00),
    "gpt-4o-mini":               (0.15,   0.60),
    "gpt-4o-2024-11-20":         (2.50,  10.00),
    "gpt-4.5-preview":           (75.00, 150.00),
    # OpenAI — reasoning models (charged on total tokens incl. reasoning tokens)
    "o1":                        (15.00,  60.00),
    "o1-mini":                   (3.00,   12.00),
    "o1-pro":                    (150.00, 600.00),
    "o3":                        (10.00,  40.00),
    "o3-mini":                   (1.10,    4.40),
    "o4-mini":                   (1.10,    4.40),
    # Anthropic
    "claude-opus-4-6":           (15.00,  75.00),
    "claude-sonnet-4-6":         (3.00,   15.00),
    "claude-haiku-4-5-20251001": (0.80,    4.00),
    # Google Gemini
    "gemini-1.5-pro":            (1.25,    5.00),
    "gemini-1.5-flash":          (0.075,   0.30),
    "gemini-2.0-flash":          (0.10,    0.40),
}


@dataclass
class TokenCounter:
    prompt_tokens: int = field(default=0)
    completion_tokens: int = field(default=0)
    _calls: int = field(default=0)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, usage) -> None:
        """Accept an LLMResponse, openai CompletionUsage, or any duck-typed object."""
        if usage is None:
            return
        self.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
        self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0
        self._calls += 1

    def report(self) -> None:
        from config import LLM_PROVIDER, OPENAI_MODEL, ANTHROPIC_MODEL, GEMINI_MODEL

        model_map = {
            "openai":    OPENAI_MODEL,
            "anthropic": ANTHROPIC_MODEL,
            "gemini":    GEMINI_MODEL,
        }
        model = model_map.get(LLM_PROVIDER, "unknown")
        prompt_rate, completion_rate = _COST_RATES.get(model, (2.50, 10.00))

        prompt_cost = self.prompt_tokens / 1_000_000 * prompt_rate
        completion_cost = self.completion_tokens / 1_000_000 * completion_rate
        total_cost = prompt_cost + completion_cost

        print("\n--- Token usage ---")
        print(f"  Provider       : {LLM_PROVIDER}/{model}")
        print(f"  API calls      : {self._calls}")
        print(f"  Prompt tokens  : {self.prompt_tokens:,}")
        print(f"  Completion     : {self.completion_tokens:,}")
        print(f"  Total          : {self.total_tokens:,}")
        print(f"  Est. cost      : ~${total_cost:.4f}")
        print("-------------------\n")

    def reset(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self._calls = 0


# Module-level singleton — import this everywhere
token_counter = TokenCounter()
