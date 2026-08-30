"""Token counting utilities for prompt and evidence budget management."""

from __future__ import annotations

import tiktoken


def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    """Returns exact token count for input text using tiktoken."""
    if not text:
        return 0
    try:
        enc = tiktoken.get_encoding(encoding_name)
        return len(enc.encode(text))
    except Exception:
        # Heuristic fallback (approx 4 chars per token)
        return max(1, len(text) // 4)
