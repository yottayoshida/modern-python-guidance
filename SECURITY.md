# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a vulnerability

If you discover a security vulnerability in modern-python-guidance, please report it responsibly:

1. **Do not** open a public issue
2. Email [i.yoshida@raksul.com](mailto:i.yoshida@raksul.com) with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
3. You will receive a response within 72 hours

## Security scope

This project is a **read-only reference tool** — it reads markdown files and outputs JSON. It does not:
- Execute any Python code from the guides
- Make network requests
- Write to the filesystem
- Process untrusted input beyond CLI arguments

The primary security consideration is **supply chain**: ensuring that the guides themselves do not recommend insecure patterns. Two guides specifically address security:
- `no-pickle` — warns against `pickle.load()` with untrusted data
- `safe-subprocess` — warns against `shell=True` and `os.system()`

## Dependencies

This project has a single runtime dependency:
- `packaging` — Python version specifier parsing (maintained by the PyPA)
