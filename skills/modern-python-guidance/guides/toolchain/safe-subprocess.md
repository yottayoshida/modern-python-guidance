---
id: safe-subprocess
title: Use subprocess Safely with List Arguments
category: toolchain
layer: 3
tags:
  - security
  - subprocess
  - shell-injection
aliases:
  - subprocess
  - os.system
  - shell=True
  - subprocess.run
python: ">=3.9"
frequency: high
detect-patterns:
  - "os\.system\("
  - "shell\s*=\s*True"
---

# Use subprocess Safely

Always pass commands as a list of arguments. Never use `shell=True` or `os.system()` with user input.

## BAD

```python
import os
import subprocess

def convert(input_path: str, output_path: str) -> None:
    os.system(f"ffmpeg -i {input_path} {output_path}")

def run_tool(filename: str) -> str:
    result = subprocess.run(
        f"grep -r {filename} src/",
        shell=True, capture_output=True, text=True,
    )
    return result.stdout
```

## GOOD

```python
import subprocess

def convert(input_path: str, output_path: str) -> None:
    subprocess.run(
        ["ffmpeg", "-i", input_path, output_path],
        check=True,
    )

def run_tool(filename: str) -> str:
    result = subprocess.run(
        ["grep", "-r", filename, "src/"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout
```

## Why

- `shell=True` passes the command through the shell — user input can inject arbitrary commands
- `os.system()` always uses the shell and is even worse (no output capture, no error handling)
- List arguments bypass the shell entirely — each element is a separate argv entry
- `check=True` raises `CalledProcessError` on non-zero exit instead of silently continuing
- `capture_output=True` is a shorthand for `stdout=PIPE, stderr=PIPE`

## When shell=True Is Acceptable

| Scenario | Acceptable? | Alternative |
|----------|-------------|-------------|
| Hardcoded command, no user input | Tolerable | Still prefer list form |
| Pipes (`cmd1 | cmd2`) | Acceptable | Use `subprocess.PIPE` between two `Popen` calls |
| Glob expansion (`*.txt`) | Acceptable | Use `pathlib.Path.glob()` |
| User-provided input in command | Never | List form only |

## References

- [subprocess — Security Considerations](https://docs.python.org/3/library/subprocess.html#security-considerations)
- [CWE-78: OS Command Injection](https://cwe.mitre.org/data/definitions/78.html)
