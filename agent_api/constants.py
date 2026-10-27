STREAMING_RESPONSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

# AgentCore Memory only accepts letters, digits, '-' and '_' in actor and session IDs.
ACTOR_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
SESSION_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
TASK_ID_PATTERN = r"^T-[0-9a-f]{8}$"
MAX_PROMPT_LENGTH = 4000
MAX_TAG_LENGTH = 30
