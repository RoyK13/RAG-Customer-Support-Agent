"""Dataset registry. A dataset is a directory under data/ with a dataset.yaml file.

Nothing in the codebase knows about a specific dataset. Everything that differs
between datasets lives in its dataset.yaml.
"""

import json
import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.config import get_settings

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,40}$")


class SourceInfo(BaseModel):
    label: str
    url: str | None = None


class LicenseInfo(BaseModel):
    name: str
    url: str | None = None


class SourceUrlConfig(BaseModel):
    # "path": file path relative to the dataset dir.
    # "mkdocs": base_url + page path in MkDocs directory URL style.
    style: str = "path"
    base_url: str | None = None


class ChunkingConfig(BaseModel):
    max_chars: int = 1600
    min_chars: int = 200


class DatasetConfig(BaseModel):
    name: str
    display_name: str
    description: str
    source: SourceInfo
    license: LicenseInfo
    notice: str | None = None
    docs_dir: str = "docs"
    source_url: SourceUrlConfig = Field(default_factory=SourceUrlConfig)
    markdown_flavor: str = "plain"
    include_root: str | None = None
    exclude: list[str] = Field(default_factory=list)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    persona: str
    examples: list[str] = Field(default_factory=list)
    path: Path

    @property
    def docs_path(self) -> Path:
        return self.path / self.docs_dir

    @property
    def collection(self) -> str:
        return f"docs_{self.name}"


def load_dataset(path: Path) -> DatasetConfig:
    raw = yaml.safe_load((path / "dataset.yaml").read_text(encoding="utf-8"))
    examples_file = path / "examples.json"
    examples = json.loads(examples_file.read_text(encoding="utf-8")) if examples_file.exists() else []
    cfg = DatasetConfig(**raw, examples=examples, path=path)
    if cfg.name != path.name or not NAME_RE.match(cfg.name):
        raise ValueError(f"dataset name {cfg.name!r} must match its directory name and be lowercase")
    return cfg


@lru_cache
def all_datasets(data_dir: Path | None = None) -> dict[str, DatasetConfig]:
    data_dir = data_dir or get_settings().data_dir
    found = {}
    for child in sorted(Path(data_dir).iterdir()):
        if (child / "dataset.yaml").exists():
            cfg = load_dataset(child)
            found[cfg.name] = cfg
    return found


def get_dataset(name: str) -> DatasetConfig | None:
    return all_datasets().get(name)
