#!/usr/bin/env python3
"""Build/update a single-file HTML wiki from repository Markdown files.

Usage:
  python3 scripts/build_wiki.py

The script updates the JSON payload inside wiki/index.html if the template already
exists. If it does not exist, a minimal fallback page is generated.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import posixpath
import re
from pathlib import Path, PurePosixPath
from typing import Iterable
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
WIKI_DIR = ROOT / "wiki"
OUTPUT_HTML = WIKI_DIR / "index.html"

EXCLUDED_DIR_NAMES = {
    ".git",
    ".pytest_cache",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    "wiki",
}

# Wiki scope is intentionally constrained to approved documentation areas.
INCLUDED_PATH_PREFIXES = {
    "docs/",
    "BackgroundProcessingInstances/docs/",
    "BackgroundProcessingInstances/EmailIntakeWorker/docs/",
    "BackgroundProcessingInstances/SchedulerNotificationWorker/docs/",
    "BackgroundProcessingInstances/OcrEngine/docs/",
    "BackgroundProcessingInstances/ExtractionWorker/docs/",
    "CoreInstances/docs/",
    "CoreInstances/ApiServer/docs/",
    "CoreInstances/FrontendWebServer/docs/",
    "nanoBanana/",
    "Storyboard/",
    "StorageConfigurationInstances/",
    "ExternalSharedInstances/",
}

INCLUDED_EXACT_PATHS: set[str] = {
    "README.md",
    "HighLevelDesignSpecification.md",
    "DOCKER.md",
    "OPEN_ISSUES.md",
    "BackgroundProcessingInstances/README.md",
    "BackgroundProcessingInstances/EmailIntakeWorker/README.md",
    "BackgroundProcessingInstances/SchedulerNotificationWorker/README.md",
    "BackgroundProcessingInstances/OcrEngine/README.md",
    "BackgroundProcessingInstances/ExtractionWorker/README.md",
    "CoreInstances/README.md",
    "CoreInstances/ApiServer/README.md",
    "CoreInstances/FrontendWebServer/README.md",
}


def should_skip_path(path: Path) -> bool:
    return any(part in EXCLUDED_DIR_NAMES for part in path.parts)


def is_in_documentation_scope(path: Path) -> bool:
    rel = path.as_posix()
    if rel in INCLUDED_EXACT_PATHS:
        return True
    return any(rel.startswith(prefix) for prefix in INCLUDED_PATH_PREFIXES)


def discover_markdown_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for md in root.rglob("*.md"):
        rel = md.relative_to(root)
        if should_skip_path(rel):
            continue
        if not is_in_documentation_scope(rel):
            continue
        files.append(md)
    return sorted(files)


def slugify(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text or "section"


def split_table_row(line: str) -> list[str]:
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [cell.strip() for cell in row.split("|")]


def is_table_separator(line: str) -> bool:
    return bool(re.match(r"^\s*\|?[\s:-]+\|[\s|:-]*\s*$", line))


def is_heading(line: str) -> bool:
    return bool(re.match(r"^\s{0,3}#{1,6}\s+", line))


def is_code_fence(line: str) -> bool:
    return bool(re.match(r"^\s*```", line))


def is_ul_item(line: str) -> bool:
    return bool(re.match(r"^\s*[-*+]\s+", line))


def is_ol_item(line: str) -> bool:
    return bool(re.match(r"^\s*\d+\.\s+", line))


_UL_RE = re.compile(r"^(\s*)([-*+])\s+(.*)$")
_OL_RE = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")
_TASK_RE = re.compile(r"^\[([ xX])\]\s+(.*)$")


def list_item_match(line: str) -> tuple[int, bool, str] | None:
    """Return (indent, ordered, content) for a list-item line, or None.

    indent is the count of leading whitespace characters before the marker.
    """
    m = _OL_RE.match(line)
    if m:
        return len(m.group(1)), True, m.group(3)
    m = _UL_RE.match(line)
    if m:
        return len(m.group(1)), False, m.group(3)
    return None


def is_blockquote(line: str) -> bool:
    return bool(re.match(r"^\s*>", line))


def is_hr(line: str) -> bool:
    return bool(re.match(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$", line))


def resolve_relative_path(current_doc: str, target: str) -> str:
    base = PurePosixPath(current_doc).parent.as_posix()
    resolved = posixpath.normpath(posixpath.join(base, target))
    return resolved


def strip_link_title(target: str) -> str:
    target = target.strip()
    if target.startswith("<") and target.endswith(">"):
        return target[1:-1]
    parts = target.split()
    if len(parts) > 1 and not target.startswith("http"):
        return parts[0]
    return target


def rewrite_link(target: str, current_doc: str, doc_paths: set[str]) -> tuple[str, bool]:
    target = strip_link_title(target)
    if not target:
        return target, False

    if target.startswith("mailto:"):
        return target, True
    if target.startswith("http://") or target.startswith("https://"):
        return target, True

    if target.startswith("#"):
        anchor = target[1:]
        route = f"#/{'/'.join(quote(part) for part in current_doc.split('/'))}"
        if anchor:
            route += f"?anchor={quote(anchor)}"
        return route, False

    anchor = ""
    base = target
    if "#" in target:
        base, anchor = target.split("#", 1)

    if base.lower().endswith(".md"):
        resolved = resolve_relative_path(current_doc, base)
        route = f"#/{'/'.join(quote(part) for part in resolved.split('/'))}"
        if anchor:
            route += f"?anchor={quote(anchor)}"
        return route, False

    if base.startswith("/"):
        return f"..{base}", False

    if base:
        resolved = resolve_relative_path(current_doc, base)
        if resolved in doc_paths:
            route = f"#/{'/'.join(quote(part) for part in resolved.split('/'))}"
            if anchor:
                route += f"?anchor={quote(anchor)}"
            return route, False
        return f"../{resolved}", False

    return target, False


def apply_inline_markdown(text: str, current_doc: str, doc_paths: set[str]) -> str:
    escaped = html.escape(text)

    code_tokens: list[str] = []

    def code_repl(match: re.Match[str]) -> str:
        code_tokens.append(f"<code>{match.group(1)}</code>")
        return f"@@CODE{len(code_tokens)-1}@@"

    escaped = re.sub(r"`([^`]+)`", code_repl, escaped)

    def image_repl(match: re.Match[str]) -> str:
        alt_text = match.group(1)
        raw_target = html.unescape(match.group(2))
        href, _ = rewrite_link(raw_target, current_doc, doc_paths)
        return (
            f'<img src="{html.escape(href, quote=True)}" '
            f'alt="{alt_text}" loading="lazy">'
        )

    escaped = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", image_repl, escaped)

    def link_repl(match: re.Match[str]) -> str:
        label = match.group(1)
        raw_target = html.unescape(match.group(2))
        href, external = rewrite_link(raw_target, current_doc, doc_paths)
        attrs = ' target="_blank" rel="noopener noreferrer"' if external else ""
        return f'<a href="{html.escape(href, quote=True)}"{attrs}>{label}</a>'

    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, escaped)

    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)

    for idx, token in enumerate(code_tokens):
        escaped = escaped.replace(f"@@CODE{idx}@@", token)

    return escaped


def render_list_item_content(
    text: str, current_doc: str, doc_paths: set[str]
) -> str:
    """Render the inline content of a single <li>.

    Detects GitHub-style task list markers (`[ ]`, `[x]`) at the start and
    emits a disabled checkbox prefix, then runs the rest through the inline
    pipeline. The check must run BEFORE inline-escape so the literal `[` is
    matched, not its HTML-escaped form.
    """
    task = _TASK_RE.match(text)
    if task:
        checked = task.group(1).lower() == "x"
        rest = task.group(2)
        checkbox = (
            '<input type="checkbox" disabled checked> '
            if checked
            else '<input type="checkbox" disabled> '
        )
        return checkbox + apply_inline_markdown(rest, current_doc, doc_paths)
    return apply_inline_markdown(text, current_doc, doc_paths)


def render_list(
    lines: list[str],
    i: int,
    base_indent: int,
    current_doc: str,
    doc_paths: set[str],
) -> tuple[str, int]:
    """Render a (possibly nested) list block starting at lines[i].

    The list's marker indent must be >= base_indent. The list ends when we
    hit a non-list line that is not a deeper-indented continuation, or a
    list-item line whose indent is < the indent of the first item.

    Returns (html, new_i). Recurses into render_list when a deeper-indented
    list-item line follows the current item.
    """
    first = list_item_match(lines[i])
    if first is None:
        return "", i
    list_indent, ordered, _content = first
    tag = "ol" if ordered else "ul"
    parts: list[str] = [f"<{tag}>"]

    while i < len(lines):
        match = list_item_match(lines[i])
        if match is None:
            # Allow blank lines between items (do not terminate the list).
            if i < len(lines) and not lines[i].strip():
                # Look ahead: only continue if the next non-blank line is
                # another item at this indent OR a deeper-indented continuation.
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j >= len(lines):
                    break
                nxt = list_item_match(lines[j])
                if nxt is not None and nxt[0] == list_indent:
                    i = j
                    continue
                if lines[j].startswith(" " * (list_indent + 1)):
                    # Deeper-indented non-list continuation belongs to the
                    # previous <li>; advance and let the inner loop pick it up.
                    i = j
                    continue
                break
            break

        indent, item_ordered, content = match
        if indent < list_indent:
            break
        if indent > list_indent:
            # Should have been consumed by the recursive call below.
            break

        i += 1
        # Collect plain (non-list) continuation lines indented deeper than
        # the current item's marker. A deeper-indented list-item line breaks
        # the loop and is handled as a nested list.
        continuation: list[str] = []
        nested_html_parts: list[str] = []
        while i < len(lines):
            nxt_line = lines[i]
            if not nxt_line.strip():
                # Blank line: peek to decide if continuation/nested continues.
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j >= len(lines):
                    break
                if not lines[j].startswith(" " * (list_indent + 1)):
                    break
                # Belongs to this item; skip the blank(s).
                i = j
                continue

            nxt_match = list_item_match(nxt_line)
            if nxt_match is not None and nxt_match[0] > list_indent:
                # Nested list under the current item.
                nested_html, i = render_list(
                    lines, i, list_indent + 1, current_doc, doc_paths
                )
                nested_html_parts.append(nested_html)
                continue
            if nxt_match is not None:
                # Sibling or shallower item: break out of continuation loop.
                break
            if nxt_line.startswith(" " * (list_indent + 1)):
                continuation.append(nxt_line.strip())
                i += 1
                continue
            break

        full_text = " ".join([content.strip()] + continuation).strip()
        item_html = render_list_item_content(full_text, current_doc, doc_paths)
        if nested_html_parts:
            item_html = item_html + "".join(nested_html_parts)
        parts.append(f"<li>{item_html}</li>")

    parts.append(f"</{tag}>")
    return "\n".join(parts), i


def render_markdown(markdown_text: str, current_doc: str, doc_paths: set[str]) -> tuple[str, list[dict[str, str]]]:
    lines = markdown_text.splitlines()
    out: list[str] = []
    headings: list[dict[str, str]] = []
    i = 0

    def is_block_boundary(line: str) -> bool:
        return (
            not line.strip()
            or is_heading(line)
            or is_code_fence(line)
            or is_ul_item(line)
            or is_ol_item(line)
            or is_blockquote(line)
            or is_hr(line)
        )

    while i < len(lines):
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        if is_code_fence(line):
            lang = line.strip()[3:].strip()
            i += 1
            code_lines: list[str] = []
            while i < len(lines) and not is_code_fence(lines[i]):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines) and is_code_fence(lines[i]):
                i += 1
            class_attr = f' class="language-{html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{class_attr}>{html.escape(chr(10).join(code_lines))}</code></pre>")
            continue

        heading_match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
        if heading_match:
            level = len(heading_match.group(1))
            raw_heading = heading_match.group(2).strip()
            heading_text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", raw_heading)
            anchor = slugify(heading_text)
            headings.append({"level": str(level), "text": heading_text, "id": anchor})
            out.append(
                f"<h{level} id=\"{anchor}\">"
                f"{apply_inline_markdown(raw_heading, current_doc, doc_paths)}"
                f"</h{level}>"
            )
            i += 1
            continue

        if "|" in line and i + 1 < len(lines) and is_table_separator(lines[i + 1]):
            header = split_table_row(line)
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(split_table_row(lines[i]))
                i += 1

            out.append("<table><thead><tr>")
            for cell in header:
                out.append(f"<th>{apply_inline_markdown(cell, current_doc, doc_paths)}</th>")
            out.append("</tr></thead><tbody>")
            for row in rows:
                out.append("<tr>")
                for cell in row:
                    out.append(f"<td>{apply_inline_markdown(cell, current_doc, doc_paths)}</td>")
                out.append("</tr>")
            out.append("</tbody></table>")
            continue

        if is_hr(line):
            out.append("<hr>")
            i += 1
            continue

        if is_ul_item(line) or is_ol_item(line):
            list_html, i = render_list(lines, i, 0, current_doc, doc_paths)
            out.append(list_html)
            continue

        if is_blockquote(line):
            quoted: list[str] = []
            while i < len(lines) and is_blockquote(lines[i]):
                quoted.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner_html, _ = render_markdown("\n".join(quoted), current_doc, doc_paths)
            out.append(f"<blockquote>{inner_html}</blockquote>")
            continue

        paragraph_parts = [line.strip()]
        i += 1
        while i < len(lines) and not is_block_boundary(lines[i]):
            paragraph_parts.append(lines[i].strip())
            i += 1
        paragraph = " ".join(part for part in paragraph_parts if part)
        out.append(f"<p>{apply_inline_markdown(paragraph, current_doc, doc_paths)}</p>")

    return "\n".join(out), headings


def extract_title(markdown_text: str, fallback: str) -> str:
    for line in markdown_text.splitlines():
        m = re.match(r"^\s*#\s+(.+?)\s*$", line)
        if m:
            return m.group(1).strip()
    return fallback


def build_docs_payload(markdown_files: Iterable[Path]) -> dict:
    docs: list[dict] = []
    rel_paths = [path.relative_to(ROOT).as_posix() for path in markdown_files]
    rel_set = set(rel_paths)

    for rel_path in rel_paths:
        md_path = ROOT / rel_path
        markdown_text = md_path.read_text(encoding="utf-8")
        html_body, headings = render_markdown(markdown_text, rel_path, rel_set)
        title = extract_title(markdown_text, PurePosixPath(rel_path).name)
        docs.append(
            {
                "path": rel_path,
                "title": title,
                "html": html_body,
                "headings": headings,
                "text": re.sub(r"\s+", " ", markdown_text).strip(),
            }
        )

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "doc_count": len(docs),
        "docs": docs,
    }


def fallback_html(payload: dict) -> str:
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>CityOfLaredoProject Wiki</title>
</head>
<body>
  <h1>CityOfLaredoProject Wiki</h1>
  <p>Open <code>wiki/index.html</code> generated with embedded payload.</p>
  <script id=\"wiki-data\" type=\"application/json\">{data_json}</script>
</body>
</html>
"""


def build_html(payload: dict, existing_html: str | None) -> str:
    data_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    if existing_html:
        pattern = re.compile(
            r'(<script id="wiki-data" type="application/json">)(.*?)(</script>)',
            flags=re.DOTALL,
        )
        if pattern.search(existing_html):
            return pattern.sub(
                lambda match: f"{match.group(1)}{data_json}{match.group(3)}",
                existing_html,
                count=1,
            )

    return fallback_html(payload)


def main() -> None:
    markdown_files = discover_markdown_files(ROOT)
    payload = build_docs_payload(markdown_files)

    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    existing_html = OUTPUT_HTML.read_text(encoding="utf-8") if OUTPUT_HTML.exists() else None
    OUTPUT_HTML.write_text(build_html(payload, existing_html), encoding="utf-8")

    print(f"Built wiki: {OUTPUT_HTML}")
    print(f"Markdown docs indexed: {payload['doc_count']}")


if __name__ == "__main__":
    main()
