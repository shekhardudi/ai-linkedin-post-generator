"""Prompt template loader.

Each .txt file in this directory is a single prompt template. They are loaded
with str.format-style {placeholders} so callers control variable substitution.
"""

from pathlib import Path


_DIR = Path(__file__).parent


def load(name: str) -> str:
    """Read a prompt template by basename (no extension)."""
    path = _DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"prompt not found: {path}")
    return path.read_text(encoding="utf-8")
