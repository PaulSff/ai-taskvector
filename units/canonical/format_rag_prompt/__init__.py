"""FormatRagPrompt unit: RAG results table → formatted prompt block string."""
from units.canonical.format_rag_prompt.format_rag_prompt import (
    FORMAT_RAG_PROMPT_INPUT_PORTS,
    FORMAT_RAG_PROMPT_OUTPUT_PORTS,
    register_format_rag_prompt,
)

__all__ = ["register_format_rag_prompt", "FORMAT_RAG_PROMPT_INPUT_PORTS", "FORMAT_RAG_PROMPT_OUTPUT_PORTS"]
