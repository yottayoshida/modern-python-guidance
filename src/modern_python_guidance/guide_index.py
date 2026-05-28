"""Dynamic guide scanner — builds in-memory index from guides/ directory."""

from __future__ import annotations

import importlib.resources
import logging
from dataclasses import dataclass, field
from itertools import zip_longest
from pathlib import Path

from modern_python_guidance.frontmatter import FrontmatterError, GuideMeta, parse_frontmatter

log = logging.getLogger(__name__)


@dataclass
class Guide:
    meta: GuideMeta
    body: str
    source_path: str
    snippet: str = ""


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
                snippet=_extract_snippet(body),
            )
        except FrontmatterError as e:
            log.warning("Skipping %s: %s", md_file, e)
        except Exception as e:
            log.warning("Unexpected error loading %s: %s", md_file, e)

    log.debug("Loaded %d guides from %s", len(index), guides_dir)
    return index


def _extract_snippet(body: str) -> str:
    """Extract a BAD → GOOD one-liner from guide body.

    Finds the first pair of lines from BAD and GOOD code blocks that differ,
    which best conveys the transformation the guide teaches.
    """
    bad_lines = _code_lines(body, "## BAD")
    good_lines = _code_lines(body, "## GOOD")
    if not bad_lines or not good_lines:
        return ""
    for b, g in zip_longest(bad_lines, good_lines, fillvalue=""):
        if b != g:
            return f"{b} → {g}" if b and g else (b or g)
    return f"{bad_lines[0]} → {good_lines[0]}"


def _code_lines(body: str, heading: str) -> list[str]:
    """Return all non-empty code lines from the first fence under a heading."""
    parts = body.split(heading + "\n")
    if len(parts) < 2:
        return []
    section = parts[1].split("\n## ")[0]
    in_fence = False
    lines: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_fence:
                in_fence = True
                continue
            break
        if in_fence and stripped:
            lines.append(stripped)
    return lines


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
