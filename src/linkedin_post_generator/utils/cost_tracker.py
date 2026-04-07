import tiktoken


class CostTracker:
    """Estimates GPT-4o API costs based on token usage."""

    GPT4O_INPUT_PER_M = 5.00    # USD per 1M input tokens
    GPT4O_OUTPUT_PER_M = 15.00  # USD per 1M output tokens

    def __init__(self):
        self._input_tokens = 0
        self._output_tokens = 0
        self._encoding = tiktoken.get_encoding("cl100k_base")

    def estimate_tokens(self, text: str) -> int:
        return len(self._encoding.encode(text))

    def add_usage(self, input_tokens: int, output_tokens: int):
        self._input_tokens += input_tokens
        self._output_tokens += output_tokens

    def add_text(self, input_text: str = "", output_text: str = ""):
        """Convenience method: estimate tokens from raw text and add to totals."""
        self.add_usage(
            self.estimate_tokens(input_text),
            self.estimate_tokens(output_text),
        )

    def get_summary(self) -> dict:
        input_cost = (self._input_tokens / 1_000_000) * self.GPT4O_INPUT_PER_M
        output_cost = (self._output_tokens / 1_000_000) * self.GPT4O_OUTPUT_PER_M
        return {
            "input_tokens": self._input_tokens,
            "output_tokens": self._output_tokens,
            "total_tokens": self._input_tokens + self._output_tokens,
            "estimated_cost_usd": round(input_cost + output_cost, 4),
        }

    def reset(self):
        self._input_tokens = 0
        self._output_tokens = 0
