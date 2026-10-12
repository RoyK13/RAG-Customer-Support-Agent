"""Fetch FastAPI's English documentation at a pinned release.

    python -m ingest.fetch_fastapi            # pinned tag
    python -m ingest.fetch_fastapi --tag X    # another tag

Downloads the release tarball from GitHub and extracts only docs/en/docs (the
Markdown pages), docs_src (code examples the pages include), and LICENSE into
data/fastapi/raw/. Records the tag, commit SHA, and fetch date in
data/fastapi/SOURCE.md. The raw files are not committed; this script reproduces them.

FastAPI is MIT licensed, Copyright (c) 2018 Sebastián Ramírez.
"""

import argparse
import io
import shutil
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import httpx

REPO = "fastapi/fastapi"
PINNED_TAG = "0.143.0"
DATASET_DIR = Path(__file__).resolve().parent.parent / "data" / "fastapi"
RAW_DIR = DATASET_DIR / "raw"
KEEP_PREFIXES = ("docs/en/docs/", "docs_src/")
KEEP_FILES = ("LICENSE",)
MAX_TARBALL_BYTES = 200 * 1024 * 1024


def resolve_commit(client: httpx.Client, tag: str) -> str:
    resp = client.get(f"https://api.github.com/repos/{REPO}/commits/{tag}",
                      headers={"Accept": "application/vnd.github+json"})
    resp.raise_for_status()
    return resp.json()["sha"]


def download_tarball(client: httpx.Client, tag: str) -> bytes:
    url = f"https://codeload.github.com/{REPO}/tar.gz/refs/tags/{tag}"
    buf = io.BytesIO()
    with client.stream("GET", url) as resp:
        resp.raise_for_status()
        for part in resp.iter_bytes():
            buf.write(part)
            if buf.tell() > MAX_TARBALL_BYTES:
                raise RuntimeError("tarball larger than expected, aborting")
    return buf.getvalue()


def extract(tar_bytes: bytes, dest: Path) -> int:
    count = 0
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue  # skip directories, symlinks, and devices
            parts = PurePosixPath(member.name).parts[1:]  # drop the "fastapi-<tag>/" prefix
            if not parts or ".." in parts:
                continue
            rel = PurePosixPath(*parts).as_posix()
            if not (rel.startswith(KEEP_PREFIXES) or rel in KEEP_FILES):
                continue
            target = (dest / rel).resolve()
            if not target.is_relative_to(dest.resolve()):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                continue
            target.write_bytes(source.read())
            count += 1
    return count


def write_source_md(tag: str, sha: str, fetched: datetime, md_files: int, total_files: int) -> None:
    (DATASET_DIR / "SOURCE.md").write_text(
        f"""# Source

This dataset is built from the English documentation in the FastAPI repository.

- Repository: https://github.com/{REPO}
- Tag: `{tag}`
- Commit SHA: `{sha}`
- Fetched: {fetched.strftime('%Y-%m-%d %H:%M UTC')}
- Paths: `docs/en/docs/` ({md_files} Markdown pages) and `docs_src/` (code examples included by the pages), {total_files} files in total
- License: MIT, see `LICENSE` in this directory
- Published docs: https://fastapi.tiangolo.com

The raw files are not committed. Reproduce them with:

```
python -m ingest.fetch_fastapi --tag {tag}
```

This is an unofficial demo using FastAPI's public documentation. It is not affiliated with or endorsed by the FastAPI project.
""",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", default=PINNED_TAG)
    args = parser.parse_args(argv)

    with httpx.Client(timeout=120, follow_redirects=True, headers={"User-Agent": "support-agent-fetch"}) as client:
        sha = resolve_commit(client, args.tag)
        print(f"FastAPI {args.tag} is commit {sha}. Downloading tarball...")
        data = download_tarball(client, args.tag)
    print(f"Downloaded {len(data) / 1e6:.1f} MB")

    if RAW_DIR.exists():
        shutil.rmtree(RAW_DIR)
    RAW_DIR.mkdir(parents=True)
    total = extract(data, RAW_DIR)
    md_files = len(list((RAW_DIR / "docs" / "en" / "docs").rglob("*.md")))
    shutil.copyfile(RAW_DIR / "LICENSE", DATASET_DIR / "LICENSE")
    write_source_md(args.tag, sha, datetime.now(UTC), md_files, total)
    print(f"Extracted {total} files ({md_files} Markdown pages) into {RAW_DIR}")
    print(f"Wrote {DATASET_DIR / 'SOURCE.md'} and {DATASET_DIR / 'LICENSE'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
