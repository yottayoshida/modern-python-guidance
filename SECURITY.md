# Security Policy and Trust Boundaries

## Supported versions

<!-- supported-release-line: 0.5.x -->

| Release line | Security fixes |
|---|---|
| 0.5.x | Supported |
| < 0.5 | Unsupported; upgrade before requesting a fix |

While modern-python-guidance is pre-1.0, security fixes are provided only for
the latest minor release line. We do not promise security backports to older
minor lines.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Use the
repository-owned private reporting form as the primary channel:

<https://github.com/yottayoshida/modern-python-guidance/security/advisories/new>

Include the impact, reproduction steps or proof of concept, affected version,
and any relevant configuration details. Do not include secrets, access tokens,
or real credentials in a report. Maintainers acknowledge and triage reports on
a best-effort basis; there is no fixed response SLA.

If GitHub Private Vulnerability Reporting is unavailable to you, use
[i.yoshida@raksul.com](mailto:i.yoshida@raksul.com) as a fallback. This
fallback mailbox is not promised to be monitored continuously.

## What mpg can change and run

`mpg setup` and `mpg uninstall` are not read-only operations. They can:

- invoke `claude mcp get`, `claude mcp add`, and `claude mcp remove` with argv
  lists and 30-second timeouts;
- create or replace mpg's symlinks under `.claude/skills/` and
  `.claude/rules/`;
- merge or unmerge only mpg's `PostToolUse` hook entry in
  `.claude/settings.local.json`, writing settings atomically; and
- remove the managed symlinks and mpg hook registration during uninstall.

The setup and uninstall paths refuse a non-symlink blocker at an mpg-managed
skill or rule path. The hook settings reader and writer refuse a symlinked
`.claude/settings.local.json`. Hook merging preserves foreign hook entries;
uninstall removes symlink entries rather than their targets, preserving the
target and unrelated configuration.

Known limitation (#170, #192): a symlinked directory on the way to a write
target is followed, not rejected. If `.claude`, `.claude/skills`, or
`.claude/rules` is a symlink, what mpg writes there lands at the link target.
This is deliberate: refusing would break "config lives elsewhere" layouts,
which are the main reason to symlink into `.claude` at all.

What following it is not is silent. Before writing anything, `mpg setup` and
`mpg uninstall` report, for each path they write, the outermost symlinked
directory on the way to it and the target that directory resolves to. Notes are
per symlinked directory, not per destination: a symlinked `.claude` is the
outermost one for all three writes and so reports once, while symlinked
`.claude/skills` and `.claude/rules` report separately even if they happen to
point at the same place. Anything reached only by following a link is inside
that other tree and is not reported.

That disclosure is not confinement. Do not treat the per-file symlink checks,
or these notes, as containment of the `.claude` tree.

## Inputs and trust boundaries

- Edited Python files and hook JSON input are untrusted. `check.py` uses
  bounded reads, tokenization, regular expressions, and `ast.parse`; it does
  not import, execute, or evaluate the edited Python.
- PostToolUse hook output names guide IDs and line numbers, not raw source
  lines, to reduce indirect prompt-injection exposure from source text.
- Python project files and dependency evidence are bounded and parsed as data.
  They may be malformed or attacker-controlled and are not trusted as code.
- MCP `project_dir` must be relative and is confined to the server working
  directory. The server working directory and the local files selected by the
  invoking user remain trusted by that user.
- Guide Markdown and packaged Rules and Skill content are trusted executable
  guidance for an agent, even though they are not Python code.
- The external `claude` process launched by setup and the user's local Claude
  configuration are outside mpg's security boundary.

mpg is not a sandbox, dependency scanner, malware scanner, or a guarantee that
generated code is safe.

## Guide supply chain

Guide changes use normal pull-request review and CI. GitHub Actions references
are SHA-pinned. Before publishing, build CI verifies the packaged Skill, Rules,
guide set, and guide index; releases publish the verified artifact. mpg does
not currently provide cryptographic guide signing or require two-person review.
