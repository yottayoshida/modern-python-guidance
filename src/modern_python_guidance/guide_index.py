"""Dynamic guide scanner — builds in-memory index from guides/ directory."""

from __future__ import annotations

import importlib.resources
import logging
from dataclasses import dataclass, field
from pathlib import Path

from modern_python_guidance.frontmatter import FrontmatterError, GuideMeta, parse_frontmatter

log = logging.getLogger(__name__)


@dataclass
class Guide:
    meta: GuideMeta
    body: str
    source_path: str


@dataclass
class GuideIndex:
    guides: dict[str, Guide] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.guides)

    def get(self, guide_id: str) -> Guide | None:
        return self.guides.get(guide_id)

    def all_meta(self) -> list[GuideMeta]:
        return [g.meta for g in self.guides.values()]

    def categories(self) -> list[str]:
        return sorted({g.meta.category for g in self.guides.values()})


def build_index(guides_dir: Path | None = None) -> GuideIndex:
    if guides_dir is None:
        guides_dir = _find_guides_dir()

    index = GuideIndex()

    if not guides_dir.is_dir():
        log.warning("Guides directory not found: %s", guides_dir)
        return index

    for md_file in sorted(guides_dir.rglob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
            meta, body = parse_frontmatter(text)

            expected_id = md_file.stem
            if meta.id != expected_id:
                log.warning(
                    "Guide ID mismatch: frontmatter says '%s', filename is '%s'"
                    " — using frontmatter ID",
                    meta.id,
                    expected_id,
                )

            if meta.id in index.guides:
                log.warning("Duplicate guide ID '%s', skipping %s", meta.id, md_file)
                continue

            index.guides[meta.id] = Guide(
                meta=meta,
                body=body,
                source_path=str(md_file),
            )
        except FrontmatterError as e:
            log.warning("Skipping %s: %s", md_file, e)
        except Exception as e:
            log.warning("Unexpected error loading %s: %s", md_file, e)

    log.debug("Loaded %d guides from %s", len(index), guides_dir)
    return index


def _find_guides_dir() -> Path:
    try:
        skills_pkg = importlib.resources.files("modern_python_guidance") / "skills"
        guides_path = skills_pkg / "modern-python-guidance" / "guides"
        traversable_path = Path(str(guides_path))
        if traversable_path.is_dir():
            return traversable_path
    except (TypeError, FileNotFoundError):
        pass

    src_root = Path(__file__).resolve().parent.parent.parent
    dev_path = src_root / "skills" / "modern-python-guidance" / "guides"
    if dev_path.is_dir():
        return dev_path

    return Path("skills") / "modern-python-guidance" / "guides"
