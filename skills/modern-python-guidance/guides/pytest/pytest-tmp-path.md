---
id: pytest-tmp-path
title: Use tmp_path Instead of tmpdir
category: pytest
layer: 2
tags:
  - pytest
  - testing
  - temporary-files
  - pathlib
aliases:
  - tmpdir
  - temp-directory
python: ">=3.9"
frequency: medium
---

# Use tmp_path Instead of tmpdir

Use the `tmp_path` fixture (returns `pathlib.Path`) instead of `tmpdir` (returns legacy `py.path.local`).

## BAD

```python
def test_write_config(tmpdir):
    config_file = tmpdir.join("config.json")
    config_file.write('{"key": "value"}')
    assert config_file.read() == '{"key": "value"}'
```

## GOOD

```python
from pathlib import Path

def test_write_config(tmp_path: Path):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"key": "value"}')
    assert config_file.read_text() == '{"key": "value"}'
```

## Why

- `tmp_path` returns `pathlib.Path`, the standard library path type
- `tmpdir` returns `py.path.local`, a legacy type from the `py` library
- `pathlib.Path` methods (`read_text`, `write_text`, `/` operator) are familiar and well-documented
- No Ruff rules cover this fixture migration -- mpg pre-generation guidance ensures `tmp_path` is used from the start

## Version Notes

- `tmp_path` available since pytest 3.9.0 (2018)
- `tmpdir` is not deprecated but is considered legacy
- `tmp_path_factory` is the session-scoped equivalent

## References

- [pytest tmp_path](https://docs.pytest.org/en/stable/how-to/tmp_path.html)
- [pathlib.Path](https://docs.python.org/3/library/pathlib.html)
