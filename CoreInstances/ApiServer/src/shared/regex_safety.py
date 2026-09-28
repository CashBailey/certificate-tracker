"""Conservative validation for administrator-supplied extraction regexes."""

import re

MAX_TEMPLATE_REGEX_LENGTH = 500

_UNSUPPORTED_CONSTRUCTS = (
    r"\\[1-9]",  # numeric backreferences
    r"\(\?P=",  # named backreferences
    r"\(\?<=",  # lookbehind
    r"\(\?<!",
    r"\(\?=",  # lookahead
    r"\(\?!",
    r"\(\?\(",  # conditionals
)


def _dangerous_group_quantifier(pattern: str, index: int) -> bool:
    """Return true for unbounded or unusually large group repetition."""
    if index >= len(pattern):
        return False
    if pattern[index] in "*+":
        return True
    if pattern[index] != "{":
        return False
    end = pattern.find("}", index + 1)
    if end == -1:
        return False
    match = re.fullmatch(r"(\d+)(?:,(\d*))?", pattern[index + 1:end])
    if not match:
        return False
    lower = int(match.group(1))
    upper_text = match.group(2)
    if "," in pattern[index + 1:end] and upper_text == "":
        return True
    upper = int(upper_text) if upper_text is not None else lower
    return upper > 100


def validate_template_regex(pattern: str) -> None:
    """Reject invalid or high-risk regex constructs before persistence."""
    if len(pattern) > MAX_TEMPLATE_REGEX_LENGTH:
        raise ValueError(
            f"Regex exceeds {MAX_TEMPLATE_REGEX_LENGTH} characters",
        )
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regex: {exc}") from exc

    if any(re.search(construct, pattern) for construct in _UNSUPPORTED_CONSTRUCTS):
        raise ValueError("Regex uses an unsupported backreference or lookaround")

    # Track whether a group already contains repetition or alternation. An
    # unbounded quantifier around either shape is a common catastrophic-
    # backtracking form such as (a+)+ or (a|aa)+.
    stack: list[dict[str, bool]] = [{"repeat": False, "alternation": False}]
    escaped = False
    in_class = False
    index = 0
    while index < len(pattern):
        char = pattern[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\":
            escaped = True
            index += 1
            continue
        if char == "[":
            in_class = True
            index += 1
            continue
        if char == "]" and in_class:
            in_class = False
            index += 1
            continue
        if in_class:
            index += 1
            continue
        if char == "(":
            stack.append({"repeat": False, "alternation": False})
        elif char == "|":
            stack[-1]["alternation"] = True
        elif char in "*+":
            stack[-1]["repeat"] = True
        elif char == "{":
            end = pattern.find("}", index + 1)
            if end != -1 and re.fullmatch(r"\d+(?:,\d*)?", pattern[index + 1:end]):
                stack[-1]["repeat"] = True
                index = end
        elif char == ")" and len(stack) > 1:
            group = stack.pop()
            stack[-1]["repeat"] = stack[-1]["repeat"] or group["repeat"]
            stack[-1]["alternation"] = (
                stack[-1]["alternation"] or group["alternation"]
            )
            next_index = index + 1
            if (
                (group["repeat"] or group["alternation"])
                and _dangerous_group_quantifier(pattern, next_index)
            ):
                raise ValueError("Regex contains a high-risk nested quantifier")
        index += 1
