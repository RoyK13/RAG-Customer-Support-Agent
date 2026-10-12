"""Markdown helpers: front matter, MkDocs syntax cleanup, and source URLs.

These are generic Markdown flavors. A dataset picks one in dataset.yaml with
`markdown_flavor`; nothing here refers to a specific dataset.
"""

import re
from pathlib import Path, PurePosixPath

import yaml

FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# MkDocs / pymdownx syntax
INCLUDE_RE = re.compile(r"^\s*\{\*\s*(\S+)(.*?)\*\}\s*$")
SNIPPET_RE = re.compile(r"""^\s*--8<--\s*["']?([^"'\s]+)["']?\s*$""")
BLOCK_OPEN_RE = re.compile(r"^\s*(/{3,})\s*([\w-]+)\s*(?:\|\s*(.*?))?\s*$")
BLOCK_CLOSE_RE = re.compile(r"^\s*(/{3,})\s*$")
LEGACY_ADMONITION_RE = re.compile(r"""^(!!!|\?\?\?\+?)\s*([\w-]+)(?:\s+"(.*?)")?\s*$""")
HEADING_ATTR_RE = re.compile(r"\s*\{\s*#[^}]*\}\s*$")
LINK_ATTR_RE = re.compile(r"\)\{[^}\n]*\}")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_RAW_BLOCK_RE = re.compile(r"<(style|script)\b[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
DIRECTIVE_RE = re.compile(r"^:::\s+\S+")  # mkdocstrings API reference directive
HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^<>]*?>")
LINE_RANGE_RE = re.compile(r"ln\[([^\]]+)\]")
TERMINAL_MARKUP_RE = re.compile(r"</?(?:font|span|u|b)\b[^>]*>")  # colour markup in rendered terminal sessions
SHELL_LANGS = {"console", "shell", "bash", "sh"}


def split_front_matter(text: str) -> tuple[dict, str]:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    meta = yaml.safe_load(match.group(1)) or {}
    return (meta if isinstance(meta, dict) else {}), text[match.end():]


def first_h1(text: str) -> str | None:
    in_code = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_code = not in_code
        elif not in_code and line.startswith("# "):
            return HEADING_ATTR_RE.sub("", line[2:]).strip()
    return None


def _select_lines(code: str, options: str) -> str:
    match = LINE_RANGE_RE.search(options)
    if not match:
        return code
    lines = code.splitlines()
    picked: list[str] = []
    for part in match.group(1).split(","):
        part = part.strip()
        if ":" in part:
            start, end = part.split(":", 1)
            picked.extend(lines[int(start or 1) - 1:int(end) if end else None])
        elif part.isdigit():
            picked.append(lines[int(part) - 1])
    return "\n".join(picked)


def _resolve_include(target: str, include_root: Path | None, sandbox: Path) -> Path | None:
    if include_root is None:
        return None
    path = (include_root / target).resolve()
    if not path.is_relative_to(sandbox.resolve()) or not path.is_file():
        return None
    return path


def clean_mkdocs(text: str, include_root: Path | None = None, sandbox: Path | None = None) -> tuple[str, dict]:
    """Resolve MkDocs includes and remove admonition and tab markers.

    Returns the cleaned text and counters for reporting.
    """
    sandbox = sandbox or include_root or Path(".")
    stats = {"includes_resolved": 0, "includes_removed": 0, "tabs_dropped": 0}
    out: list[str] = []
    lines = HTML_RAW_BLOCK_RE.sub("", HTML_COMMENT_RE.sub("", text)).splitlines()

    in_code = False
    code_lang = ""
    stack: list[str] = []  # open pymdownx blocks: "tab", "skip", or "block"
    last_closed_tab_at = -10  # index in `out` right after the last closed tab
    legacy_indent = False
    in_directive = False

    for line in lines:
        if in_directive:
            if not line.strip() or line.startswith((" ", "\t")):
                continue
            in_directive = False
        if not in_code and DIRECTIVE_RE.match(line):
            in_directive = True  # drop the directive and its indented options
            continue
        if FENCE_RE.match(line):
            in_code = not in_code
            code_lang = line.strip().lstrip("`~").strip().lower() if in_code else ""
            if "skip" not in stack:
                out.append(line[4:] if legacy_indent and line.startswith("    ") else line)
            continue
        if in_code:
            if code_lang in SHELL_LANGS:
                line = TERMINAL_MARKUP_RE.sub("", line)
            if "skip" not in stack:
                out.append(line[4:] if legacy_indent and line.startswith("    ") else line)
            continue

        # pymdownx blocks: /// type | title ... ///
        if BLOCK_CLOSE_RE.match(line) and stack:
            kind = stack.pop()
            if kind == "tab":
                last_closed_tab_at = len(out)
            continue
        opened = BLOCK_OPEN_RE.match(line)
        if opened:
            kind, title = opened.group(2).lower(), (opened.group(3) or "").strip()
            if "skip" in stack:
                stack.append("skip")
            elif kind == "tab":
                # Keep the first tab of a group, drop the alternatives.
                only_blank_since = all(not l.strip() for l in out[last_closed_tab_at:])
                if last_closed_tab_at >= 0 and only_blank_since and len(out) - last_closed_tab_at < 3:
                    stack.append("skip")
                    stats["tabs_dropped"] += 1
                else:
                    stack.append("tab")
            else:
                stack.append("block")
                label = title or kind.capitalize()
                out.append(f"**{label}:**")
            continue
        if "skip" in stack:
            continue

        # Legacy admonitions: !!! note "Title" followed by indented content
        legacy = LEGACY_ADMONITION_RE.match(line)
        if legacy:
            legacy_indent = True
            out.append(f"**{legacy.group(3) or legacy.group(2).capitalize()}:**")
            continue
        if legacy_indent:
            if line.startswith("    "):
                line = line[4:]
            elif line.strip():
                legacy_indent = False

        include = INCLUDE_RE.match(line) or SNIPPET_RE.match(line)
        if include:
            target = include.group(1)
            options = include.group(2) if include.re is INCLUDE_RE else ""
            path = _resolve_include(target, include_root, sandbox)
            if path is None:
                stats["includes_removed"] += 1
                continue
            code = _select_lines(path.read_text(encoding="utf-8"), options).rstrip()
            lang = {".py": "python", ".sh": "bash", ".json": "json", ".toml": "toml"}.get(path.suffix, "")
            out.extend([f"```{lang}", code, "```"])
            stats["includes_resolved"] += 1
            continue

        if line.lstrip().startswith("#"):
            line = HEADING_ATTR_RE.sub("", line)
        line = LINK_ATTR_RE.sub(")", line)
        line = HTML_TAG_RE.sub("", line)
        out.append(line)

    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n", stats


def build_source(rel_path: PurePosixPath, docs_dir: str, style: str, base_url: str | None) -> str:
    if style == "mkdocs" and base_url:
        parts = list(rel_path.with_suffix("").parts)
        if parts and parts[-1] == "index":
            parts = parts[:-1]
        path = "/".join(parts)
        return base_url.rstrip("/") + "/" + (path + "/" if path else "")
    return f"{docs_dir}/{rel_path.as_posix()}"
