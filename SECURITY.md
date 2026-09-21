# Security Policy and Trust Boundaries

## Supported versions

<!-- supported-release-line: none -->

mpg is no longer actively maintained. No release line receives security fixes,
including the last release, 1.3.x, and no fix is planned. Vulnerability reports
are not taken either: there is no private channel, and nobody is reading one.
Decide whether mpg is safe for your use from what it does today, which the rest
of this document describes.

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
  lines, to reduce indirect prompt-injection exposure from source text. Since
  #209 it can also return a one-line `systemMessage` for a file it could not
  check, carrying the file's path and an OS or exception message — still never
  source text — with every control, format, line and paragraph separator, and
  surrogate character shown as an escape and the JSON kept ASCII.
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

Guide changes went through pull-request review and CI. GitHub Actions references
are SHA-pinned. Before publishing, build CI verifies the packaged Skill, Rules,
guide set, and guide index; releases publish the verified artifact. mpg does
not currently provide cryptographic guide signing or require two-person review.
