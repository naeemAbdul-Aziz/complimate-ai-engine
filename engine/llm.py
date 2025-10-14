"""Deprecated module placeholder.

This file previously provided a stub LLM abstraction with a FREE_MODE option.
The production system now requires real OpenAI models only. Any legacy imports
of `engine.llm` should be removed. Keeping a minimal placeholder to avoid
ImportError during transition.
"""

raise RuntimeError(
    "engine.llm is deprecated. Remove its usage and rely on settings-based OpenAI initialisation in main pipeline."
)
