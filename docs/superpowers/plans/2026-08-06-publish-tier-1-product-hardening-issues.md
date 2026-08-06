# Publish Tier 1 Product-Hardening Issues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish and verify the five approved Tier 1 product-hardening issues in `yottayoshida/modern-python-guidance`.

**Architecture:** The approved design document is the single source for titles, bodies, and labels. Create each issue independently through the GitHub connector, then read the resulting issue snapshots back and validate count, language, labels, sections, and the #152 cross-reference.

**Tech Stack:** GitHub Issues, GitHub connector, Markdown

## Global Constraints

- Create exactly five new open issues in `yottayoshida/modern-python-guidance`.
- Use the exact titles and English bodies from `docs/superpowers/specs/2026-08-06-tier-1-product-hardening-issues-design.md`.
- Apply `tier:1-ship` plus only the labels listed for each issue in the specification.
- Do not modify, close, reopen, or relabel existing issues in this batch.
- Issue 3 must link to existing issue #152; no other new cross-reference is required.

---

### Task 1: Recheck for title duplicates

**Files:**
- Read: `docs/superpowers/specs/2026-08-06-tier-1-product-hardening-issues-design.md`
- Modify: none

**Interfaces:**
- Consumes: the five exact issue titles from the approved specification
- Produces: confirmation that no open or closed issue already has any exact title

- [ ] Search all issues in `yottayoshida/modern-python-guidance` for each exact title.
- [ ] Stop without creating anything if an exact duplicate exists.
- [ ] Confirm all requested labels exist in the repository.

### Task 2: Publish correctness and compatibility issues

**Files:**
- Read: the Issue 1 and Issue 2 sections of the approved specification
- Modify: GitHub Issues only

**Interfaces:**
- Consumes: exact Issue 1 and Issue 2 titles, bodies, and labels
- Produces: two normalized GitHub issue snapshots and URLs

- [ ] Create `Make guide applicability dependency-aware for framework and tool versions`.
- [ ] Create `Honor automatic target-Python detection across CLI and MCP guidance paths`.
- [ ] Verify both issues are open and include all specified labels and Markdown sections.

### Task 3: Publish coverage and security-contract issues

**Files:**
- Read: the Issue 3 and Issue 4 sections of the approved specification
- Modify: GitHub Issues only

**Interfaces:**
- Consumes: exact Issue 3 and Issue 4 titles, bodies, and labels
- Produces: two normalized GitHub issue snapshots and URLs

- [ ] Create `Do not claim full-catalog hook coverage while 15 guides are non-detectable`.
- [ ] Create `Update SECURITY.md to match the current setup and hook attack surface`.
- [ ] Verify Issue 3 contains a rendered reference to #152.
- [ ] Verify both issues are open and include all specified labels and Markdown sections.

### Task 4: Publish benchmark-claim issue

**Files:**
- Read: the Issue 5 section of the approved specification
- Modify: GitHub Issues only

**Interfaces:**
- Consumes: exact Issue 5 title, body, and labels
- Produces: one normalized GitHub issue snapshot and URL

- [ ] Create `Calibrate effectiveness claims to the benchmark's actual scope and delivery mechanism`.
- [ ] Verify the issue is open and includes all specified labels and Markdown sections.

### Task 5: Verify the published batch

**Files:**
- Modify: none

**Interfaces:**
- Consumes: the five created issue numbers
- Produces: a final verified list of issue URLs and priority rationale

- [ ] Fetch all five issues after creation rather than relying only on mutation responses.
- [ ] Confirm exactly five exact-title matches exist and all are open.
- [ ] Confirm all bodies are English and contain `## Problem`, `## Product impact`, `## Scope`, and `## Acceptance criteria`.
- [ ] Confirm every issue has `tier:1-ship` and its specified `area:*` labels.
- [ ] Confirm existing issues #152, #166, #167, #170, and #54 were not modified.
- [ ] Report the five URLs ordered by product risk: compatibility, version correctness, coverage contract, security contract, benchmark credibility.
