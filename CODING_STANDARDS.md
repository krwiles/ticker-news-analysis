# Coding Standards

How code in this repo should be *written* — as opposed to an ADR (a decision made) or `CONTEXT.md` (what a
term means). `code-review`'s Standards axis reads this file directly; a rule documented here always overrides
that skill's own generic smell baseline. Starts with one entry; add to it as real conventions emerge, the same
way ADRs get added one at a time rather than drafted up front.

## Comments

This is a learning project (see `README.md`) — comments here run denser than typical production code on
purpose, so the reasoning behind a piece of code stays visible without having to reconstruct it. Density is a
deliberate choice, not an oversight to trim.

- Every distinct logical step in a function gets a short comment above it — not just the steps that seem
  non-trivial. A one-line normalization, an early-return cache check, a loop, a fallback at the end — each
  gets its own one-liner. Skimming just the comments should show the whole shape of the function, top to
  bottom, without reading the code itself.
- A comment states what the block accomplishes and, where it's not obvious, why — not the mechanics already
  visible in the line(s) below it. E.g. "Normalize so lookups/cache keys are case-insensitive," not "uppercase
  the ticker."
- Keep it to one line. A second line is fine only when a real nuance would otherwise be lost — if a comment
  is stretching to three-plus lines, cut it down rather than explaining more. Skimmable in a second, not a
  paragraph to read. (Docstrings, below, can run longer.)
- Docstrings can run longer, but stay trimmed to the one or two facts a reader actually needs, not every true,
  related fact. Drop comparisons to how other functions/files do it differently, and drop mechanism-level
  detail unless it's the actual reason for the fix, not just interesting context.
- A decision that has (or will have) a full write-up elsewhere — an ADR, a spec — gets a pointer next to the
  code, not a second copy: name the decision and cite the doc (e.g. `# Flat module, not a package -- see
  docs/plans/0007-*.md.`), don't restate the justification, the evidence, or the rejected alternatives. That
  reasoning stays in the doc.
- A call whose name or return value isn't obvious from how it's used — especially a third-party/library call,
  or a terser internal helper — gets a brief note on what it actually does and returns.
- Comment at the block level, not line-by-line: one comment per logical step, even if that step is only one
  line long, not a separate comment for every line inside a multi-line block.
- Applies to test files exactly the same as source files. A descriptive test name isn't a substitute for block
  comments — test functions get the same short comment above each distinct step (arrange, mock a boundary,
  act, assert) as any other code.

**Enforced by a pre-commit hook** (`scripts/check_comment_length.py`, run via `.githooks/pre-commit`) that
blocks a commit touching a `#`/`//` comment block longer than two lines. One-time setup after cloning:
`git config core.hooksPath .githooks`. It's a line-count heuristic, not a judge of quality — it can't catch a
comment that restates mechanics instead of intent, only ones that run too long; bypass with
`git commit --no-verify` for a rare, deliberate exception.
