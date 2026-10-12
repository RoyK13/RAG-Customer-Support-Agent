from pathlib import Path

from app.datasets import load_dataset
from ingest.chunking import chunk_markdown, load_dataset_documents, pack_blocks, split_blocks
from ingest.markdown import build_source, clean_mkdocs, split_front_matter

ROOT = Path(__file__).resolve().parent.parent


def chunk(md: str, max_chars: int = 400, min_chars: int = 50):
    return chunk_markdown(md, dataset="t", doc_id="doc", doc_title="Guide", source="docs/doc.md",
                          max_chars=max_chars, min_chars=min_chars)


def test_section_paths_follow_heading_hierarchy():
    md = "# Guide\n\nIntro.\n\n## Claims\n\nClaims text.\n\n### Filing a claim\n\nFile it.\n\n## Exclusions\n\nNone.\n"
    paths = [c.section_path for c in chunk(md)]
    assert paths == ["Guide", "Guide > Claims", "Guide > Claims > Filing a claim", "Guide > Exclusions"]


def test_heading_without_body_produces_no_chunk():
    md = "# Guide\n\n## Coverage\n\n### Periods\n\nTwo years.\n"
    chunks = chunk(md)
    assert [c.section_path for c in chunks] == ["Guide > Coverage > Periods"]


def test_hash_inside_code_block_is_not_a_heading():
    md = "# Guide\n\n## Setup\n\n```python\n# install\nx = 1\n```\n"
    chunks = chunk(md)
    assert len(chunks) == 1
    assert chunks[0].section_path == "Guide > Setup"
    assert "# install" in chunks[0].text


def test_long_section_is_split_but_code_block_stays_whole():
    code = "```python\n" + "\n".join(f"line_{i} = {i}" for i in range(80)) + "\n```"
    paragraphs = "\n\n".join(f"Paragraph {i} " + "words " * 30 for i in range(6))
    md = f"# Guide\n\n## Big\n\n{paragraphs}\n\n{code}\n\nAfter the code.\n"
    chunks = chunk(md, max_chars=400)
    assert len(chunks) > 1
    holders = [c for c in chunks if "```python" in c.text]
    assert len(holders) == 1, "code block must live in exactly one chunk"
    assert holders[0].text.count("```") == 2
    assert "line_0 = 0" in holders[0].text and "line_79 = 79" in holders[0].text
    for c in chunks:
        assert c.text.count("```") % 2 == 0, "no chunk may contain half a code block"


def test_code_block_with_blank_lines_is_one_block():
    md = "Text before.\n\n```python\ndef a():\n    pass\n\n\ndef b():\n    pass\n```\n\nText after."
    blocks = split_blocks(md)
    assert blocks == ["Text before.", "```python\ndef a():\n    pass\n\n\ndef b():\n    pass\n```", "Text after."]


def test_pack_blocks_never_cuts_a_block():
    blocks = ["a" * 300, "b" * 300, "c" * 900]
    pieces = pack_blocks(blocks, max_chars=500, min_chars=10)
    assert pieces == ["a" * 300, "b" * 300, "c" * 900]


def test_chunk_ids_are_stable():
    md = "# Guide\n\n## A\n\nText.\n"
    assert [c.chunk_id for c in chunk(md)] == [c.chunk_id for c in chunk(md)]


def test_front_matter_is_parsed_and_removed():
    meta, body = split_front_matter("---\ntitle: X\nlast_updated: 2026-01-02\n---\n\n# X\n")
    assert meta["title"] == "X"
    assert body.strip() == "# X"


def test_mkdocs_admonitions_tabs_and_includes(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("line1\nline2\nline3\nline4\n", encoding="utf-8")
    md = (
        "## First Steps { #first-steps }\n\n"
        "/// tip | Good to know\n\nUse the CLI.\n\n///\n\n"
        "//// tab | Python 3.10+\n\n```python\nnew = 1\n```\n\n////\n\n"
        "//// tab | Python 3.8+\n\n```python\nold = 1\n```\n\n////\n\n"
        "{* ./src/main.py ln[2:3] hl[2] *}\n\n"
        "{* ./src/missing.py *}\n\n"
        "!!! note\n    Legacy note body.\n\n"
        'See <abbr title="Application Programming Interface">API</abbr> [docs](x.md){.internal-link target=_blank}.\n'
    )
    out, stats = clean_mkdocs(md, include_root=tmp_path, sandbox=tmp_path)
    assert "## First Steps\n" in out
    assert "///" not in out and "{*" not in out and "!!!" not in out
    assert "**Good to know:**" in out and "Use the CLI." in out
    assert "new = 1" in out and "old = 1" not in out
    assert "```python\nline2\nline3\n```" in out
    assert "Legacy note body." in out
    assert "See API [docs](x.md)." in out
    assert stats == {"includes_resolved": 1, "includes_removed": 1, "tabs_dropped": 1}


def test_include_outside_sandbox_is_removed(tmp_path):
    out, stats = clean_mkdocs("{* ../../etc/passwd *}\n", include_root=tmp_path, sandbox=tmp_path)
    assert "passwd" not in out
    assert stats["includes_removed"] == 1


def test_build_source_styles():
    from pathlib import PurePosixPath as P

    base = "https://example.com/"
    assert build_source(P("tutorial/first-steps.md"), "docs", "mkdocs", base) == "https://example.com/tutorial/first-steps/"
    assert build_source(P("tutorial/index.md"), "docs", "mkdocs", base) == "https://example.com/tutorial/"
    assert build_source(P("index.md"), "docs", "mkdocs", base) == "https://example.com/"
    assert build_source(P("a.md"), "docs", "path", None) == "docs/a.md"


def test_halden_dataset_chunks_have_required_metadata():
    cfg = load_dataset(ROOT / "data" / "halden")
    docs = load_dataset_documents(cfg)
    assert len(docs) >= 15
    for doc in docs:
        assert doc.title and doc.last_updated
        for c in doc.chunks:
            assert c.dataset == "halden" and c.doc_id == doc.doc_id
            assert c.section_path.startswith(doc.title)
            assert c.text.strip()



def test_terminal_markup_removed_only_in_shell_blocks():
    md = "\n".join([
        "```console",
        '$ <font color="#4E9A06">fastapi</font> dev <span style="x">ok</span>',
        "```",
        "",
        "```html",
        '<span class="keep">x</span>',
        "```",
        "",
        "::: fastapi.FastAPI",
        "    options:",
        "        members: []",
        "",
        "After.",
        "<style>",
        "h1 { display: none; }",
        "</style>",
    ])
    out, _ = clean_mkdocs(md)
    assert "$ fastapi dev ok" in out
    assert '<span class="keep">x</span>' in out
    assert ":::" not in out and "members" not in out and "After." in out
    assert "display: none" not in out
