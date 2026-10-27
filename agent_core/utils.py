import re

_THINK_TAG_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)

_OPEN_TAG = "<think>"
_CLOSE_TAG = "</think>"


def strip_think_tags(text: str) -> str:
    """Remove inline <think>...</think> blocks (Kimi K2 Thinking format)."""
    if not text or "<think>" not in text:
        return text
    cleaned = _THINK_TAG_PATTERN.sub("", text)
    return cleaned.lstrip("\n")


def _tag_prefix_len(text: str, tag: str) -> int:
    """Return the length of the longest suffix of *text* that is a prefix of *tag*.

    Example: text="abc<thi", tag="<think>" → returns 4 (for "<thi").
    Returns 0 if no suffix of text matches a prefix of tag.
    """
    max_check = min(len(text), len(tag) - 1)
    for length in range(max_check, 0, -1):
        if text.endswith(tag[:length]):
            return length
    return 0


class ThinkTagFilter:
    """Stateful filter that suppresses <think>...</think> across streamed chunks.

    Handles all fragmentation cases:
    - Tags split across chunk boundaries (e.g. "<thi" + "nk>")
    - Complete tags within a single chunk
    - Partial tag look-alikes that turn out not to be real tags
    """

    def __init__(self):
        self._suppressing = False
        self._buffer = ""

    def feed(self, text: str) -> str:
        """Process a chunk and return only the visible (non-think) text."""
        if not text:
            return ""

        text = self._buffer + text
        self._buffer = ""
        output_parts = []

        while text:
            if not self._suppressing:
                idx = text.find(_OPEN_TAG)
                if idx != -1:
                    # Found complete open tag — yield text before it, enter suppression
                    if idx > 0:
                        output_parts.append(text[:idx])
                    self._suppressing = True
                    text = text[idx + len(_OPEN_TAG):]
                else:
                    # Check if text ends with a partial prefix of <think>
                    plen = _tag_prefix_len(text, _OPEN_TAG)
                    if plen:
                        # Buffer the ambiguous suffix, yield the rest
                        output_parts.append(text[:-plen])
                        self._buffer = text[-plen:]
                    else:
                        output_parts.append(text)
                    break
            else:
                # Suppressing — look for close tag
                idx = text.find(_CLOSE_TAG)
                if idx != -1:
                    # Found close tag — exit suppression, continue with remainder
                    self._suppressing = False
                    text = text[idx + len(_CLOSE_TAG):]
                    # Strip leading newline after </think>
                    if text.startswith("\n"):
                        text = text[1:]
                else:
                    # Check if text ends with a partial prefix of </think>
                    plen = _tag_prefix_len(text, _CLOSE_TAG)
                    if plen:
                        self._buffer = text[-plen:]
                    # Discard all suppressed text
                    break

        return "".join(output_parts)

    def flush(self) -> str:
        """Call at end of stream to yield any buffered text that wasn't a real tag."""
        buf = self._buffer
        self._buffer = ""
        if self._suppressing:
            # Stream ended inside a think block — discard buffer
            return ""
        # Buffer was a partial tag candidate that never completed — emit it
        return buf


def extract_text_from_chunk(chunk) -> str:
    """Extract visible text from a streaming chunk.

    Handles multiple model output formats:
      - str: plain text delta (may contain inline <think> tags from Kimi)
      - list with {"type": "text"}: standard text blocks
      - list with {"type": "thinking"}: Claude extended thinking (skipped)
      - list with {"type": "reasoning_content"}: Bedrock Converse native reasoning (skipped)
    """
    if chunk is None or not hasattr(chunk, "content"):
        return ""
    content = chunk.content
    if isinstance(content, str):
        return strip_think_tags(content)
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type", "")
                if block_type == "text":
                    parts.append(block.get("text", ""))
                elif block_type in ("thinking", "reasoning_content"):
                    continue
            elif isinstance(block, str):
                parts.append(block)
        text = "".join(parts)
        return strip_think_tags(text)
    return ""
