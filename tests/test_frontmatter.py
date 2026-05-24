from __future__ import annotations

import pytest

from modern_python_guidance.frontmatter import FrontmatterError, GuideMeta, parse_frontmatter

VALID_GUIDE = """\
---
id: use-builtin-generics
title: Use Built-in Generic Types
category: typing
layer: 1
tags:
  - type-hints
  - generics
aliases:
  - typing.List
  - typing.Dict
python: ">=3.9"
frequency: high
pep: 585
---

# Use Built-in Generic Types

Body content here.
"""


def test_parse_valid_guide():
    meta, body = parse_frontmatter(VALID_GUIDE)

    assert isinstance(meta, GuideMeta)
    assert meta.id == "use-builtin-generics"
    assert meta.title == "Use Built-in Generic Types"
    assert meta.category == "typing"
    assert meta.layer == 1
    assert meta.tags == ["type-hints", "generics"]
    assert meta.aliases == ["typing.List", "typing.Dict"]
    assert meta.python == ">=3.9"
    assert meta.frequency == "high"
    assert meta.pep == [585]
    assert "Body content here." in body


def test_parse_minimal_guide():
    text = """\
---
id: minimal
title: Minimal Guide
category: stdlib
layer: 2
tags:
  - test
python: ">=3.11"
frequency: medium
---

Body.
"""
    meta, body = parse_frontmatter(text)
    assert meta.id == "minimal"
    assert meta.aliases == []
    assert meta.pep == []
    assert body == "Body."


def test_multiple_peps():
    text = """\
---
id: multi-pep
title: Multi PEP
category: typing
layer: 1
tags:
  - test
python: ">=3.10"
frequency: low
pep:
  - 585
  - 604
---

Body.
"""
    meta, _ = parse_frontmatter(text)
    assert meta.pep == [585, 604]


def test_missing_opening_fence():
    with pytest.raises(FrontmatterError, match="must start with ---"):
        parse_frontmatter("id: no-fence\n---\n")


def test_missing_closing_fence():
    with pytest.raises(FrontmatterError, match="closing --- not found"):
        parse_frontmatter("---\nid: broken\n")


def test_missing_required_field():
    text = """\
---
id: missing-fields
title: Missing
---

Body.
"""
    with pytest.raises(FrontmatterError, match="missing required fields"):
        parse_frontmatter(text)


def test_invalid_frequency():
    text = """\
---
id: bad-freq
title: Bad Freq
category: typing
layer: 1
tags:
  - test
python: ">=3.11"
frequency: critical
---
"""
    with pytest.raises(FrontmatterError, match="invalid frequency"):
        parse_frontmatter(text)


def test_invalid_layer():
    text = """\
---
id: bad-layer
title: Bad Layer
category: typing
layer: 5
tags:
  - test
python: ">=3.11"
frequency: high
---
"""
    with pytest.raises(FrontmatterError, match="layer must be 1, 2, or 3"):
        parse_frontmatter(text)


def test_duplicate_key():
    text = """\
---
id: dup
id: dup2
title: Dup
category: typing
layer: 1
tags:
  - test
python: ">=3.11"
frequency: high
---
"""
    with pytest.raises(FrontmatterError, match="duplicate key"):
        parse_frontmatter(text)


def test_unsupported_syntax():
    text = """\
---
id: bad
title: Bad
  nested: value
---
"""
    with pytest.raises(FrontmatterError, match="unsupported syntax"):
        parse_frontmatter(text)


def test_empty_tags_rejected():
    text = """\
---
id: empty-tags
title: Empty Tags
category: typing
layer: 1
tags: notalist
python: ">=3.11"
frequency: high
---
"""
    with pytest.raises(FrontmatterError, match="tags must be a non-empty list"):
        parse_frontmatter(text)


def test_quoted_string_unquoted():
    text = """\
---
id: quoted-test
title: A "quoted" title
category: typing
layer: 1
tags:
  - test
python: ">=3.9"
frequency: high
---
"""
    meta, _ = parse_frontmatter(text)
    assert meta.python == ">=3.9"


def test_empty_scalar_rejected():
    text = """\
---
id: empty-title
title:
category: typing
layer: 1
tags:
  - test
python: ">=3.9"
frequency: high
---
"""
    with pytest.raises(FrontmatterError, match="must be a scalar value"):
        parse_frontmatter(text)


def test_single_quoted_string_stripped():
    text = """\
---
id: single-quote
title: Single Quote Test
category: typing
layer: 1
tags:
  - test
python: '>=3.9'
frequency: high
---
"""
    meta, _ = parse_frontmatter(text)
    assert meta.python == ">=3.9"


def test_pep_non_integer_raises_frontmatter_error():
    text = """\
---
id: bad-pep
title: Bad PEP
category: typing
layer: 1
tags:
  - test
python: ">=3.9"
frequency: high
pep:
  - PEP-585
---
"""
    with pytest.raises(FrontmatterError, match="pep list items must be integers"):
        parse_frontmatter(text)


def test_unicode_digit_not_parsed_as_int():
    text = """\
---
id: unicode-digit
title: Unicode Digit Test
category: typing
layer: 1
tags:
  - test
python: ">=3.9"
frequency: high
pep: ٣٤٥
---
"""
    with pytest.raises(FrontmatterError, match="pep must be int or list"):
        parse_frontmatter(text)
