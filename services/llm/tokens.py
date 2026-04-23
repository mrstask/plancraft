"""Lightweight token estimation for Ollama / OpenAI-style chat payloads.

Uses a 4-char-per-token heuristic rather than adding a tokenizer dependency.
Ollama serves many different tokenizers (gemma/qwen/llama) so a single exact
count is impossible anyway; for a "how full is the context" indicator, ±15%
is accurate enough to be useful.
"""
from __future__ import annotations

from typing import Iterable, Mapping

# Per-message overhead (role tag + separators in the chat template).
_PER_MESSAGE_OVERHEAD = 4


def count_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def count_messages(messages: Iterable[Mapping[str, str]]) -> int:
    total = 0
    for m in messages:
        total += count_tokens(m.get("content", "")) + _PER_MESSAGE_OVERHEAD
    return total
