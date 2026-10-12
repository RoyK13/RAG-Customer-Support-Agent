# Source

This dataset is built from the English documentation in the FastAPI repository.

- Repository: https://github.com/fastapi/fastapi
- Tag: `0.143.0`
- Commit SHA: `f5c6e9b4f9cadc1bf0f9a1fd672e621206b63007`
- Fetched: 2026-10-11 08:41 UTC
- Paths: `docs/en/docs/` (156 Markdown pages) and `docs_src/` (code examples included by the pages), 873 files in total
- License: MIT, see `LICENSE` in this directory
- Published docs: https://fastapi.tiangolo.com

The raw files are not committed. Reproduce them with:

```
python -m ingest.fetch_fastapi --tag 0.143.0
```

This is an unofficial demo using FastAPI's public documentation. It is not affiliated with or endorsed by the FastAPI project.
