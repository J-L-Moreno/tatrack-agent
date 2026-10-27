"""Composes the final system prompt from individual sections."""

from config import AgentConfig
from prompts.sections import (
    deletion_rules,
    long_term_memory,
    progress_and_reports,
    response_style,
    role,
    safety,
    task_model,
    task_operations,
)


def build_system_prompt(cfg: AgentConfig) -> str:
    sections = [
        role(),
        task_model(cfg.user_timezone),
        task_operations(),
        deletion_rules(),
        progress_and_reports(),
    ]
    if cfg.enable_long_term_memory:
        sections.append(long_term_memory())
    sections.extend([safety(), response_style()])
    return "\n\n".join(sections)
