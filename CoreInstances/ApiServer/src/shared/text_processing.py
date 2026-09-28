"""
Text processing utilities for the City of Laredo Certificate Management System.

Functions for clustering document tokens into lines, joining them in reading order,
and building searchable text representations.
"""

from .models import DocumentToken, SearchableText


# Default threshold for clustering tokens into lines (~1.5% of page height)
LINE_HEIGHT_THRESHOLD = 0.015
PAGE_BREAK_MARKER = "[PAGE_BREAK]"


def cluster_tokens_into_lines(
    tokens: list[DocumentToken],
    line_height_threshold: float = LINE_HEIGHT_THRESHOLD,
) -> list[list[DocumentToken]]:
    """
    Cluster tokens into lines based on vertical position.

    Args:
        tokens: List of document tokens
        line_height_threshold: Maximum vertical distance to be considered same line

    Returns:
        List of lines, each containing tokens in that line
    """
    if not tokens:
        return []

    # Keep page identity ahead of geometric reading order. Coordinates are
    # page-local and must never cause tokens from different pages to share a
    # synthetic line.
    sorted_tokens = sorted(
        tokens,
        key=lambda token: (token.page_num, token.bbox_norm[1], token.bbox_norm[0]),
    )

    lines: list[list[DocumentToken]] = []
    current_line: list[DocumentToken] = [sorted_tokens[0]]

    for token in sorted_tokens[1:]:
        prev_token = current_line[-1]
        prev_y_center = (prev_token.bbox_norm[1] + prev_token.bbox_norm[3]) / 2
        curr_y_center = (token.bbox_norm[1] + token.bbox_norm[3]) / 2

        if (
            token.page_num == prev_token.page_num
            and abs(curr_y_center - prev_y_center) <= line_height_threshold
        ):
            current_line.append(token)
        else:
            lines.append(current_line)
            current_line = [token]

    if current_line:
        lines.append(current_line)

    return lines


def join_tokens_reading_order(tokens: list[DocumentToken]) -> str:
    """
    Join tokens in reading order (left-to-right, top-to-bottom).

    Args:
        tokens: List of document tokens

    Returns:
        Joined text string
    """
    full_text, _ = _render_searchable_text(tokens)
    return full_text


def _render_searchable_text(
    tokens: list[DocumentToken],
) -> tuple[str, dict[tuple[int, int], list[str]]]:
    """Render text and positions while preserving explicit page boundaries."""
    parts: list[str] = []
    token_map: dict[tuple[int, int], list[str]] = {}
    char_pos = 0
    previous_page: int | None = None

    for line in cluster_tokens_into_lines(tokens):
        page_num = line[0].page_num
        if parts:
            separator = (
                f"\n{PAGE_BREAK_MARKER}\n"
                if previous_page is not None and page_num != previous_page
                else "\n"
            )
            parts.append(separator)
            char_pos += len(separator)

        for index, token in enumerate(sorted(line, key=lambda item: item.bbox_norm[0])):
            if index:
                parts.append(" ")
                char_pos += 1
            start = char_pos
            parts.append(token.text)
            char_pos += len(token.text)
            token_map.setdefault((start, char_pos), []).append(token.token_id)

        previous_page = page_num

    return "".join(parts), token_map


def build_searchable_text(tokens: list[DocumentToken]) -> SearchableText:
    """
    Build searchable text representation with token mapping.

    Args:
        tokens: List of document tokens

    Returns:
        SearchableText object with full text and token map
    """
    full_text, token_map = _render_searchable_text(tokens)

    return SearchableText(full_text=full_text, token_map=token_map)
