#!/usr/bin/env python3
"""Flags inline comment blocks longer than 2 lines (CODING_STANDARDS.md's "Comments" rule).
Checks .py files (# comments) and .ts/.tsx files (// comments); docstrings/JSDoc are exempt.

Two modes: no args checks staged files and exits 1 on a violation (the pre-commit hook, blocking);
`--file PATH [PATH ...]` checks specific files and always exits 0 (the PostToolUse hook, advisory
-- warns without interrupting an in-progress edit).

A line starting a "Label:" pattern (e.g. "Arrange:", "Act & assert:") begins a fresh block even
with no blank line above it, so two adjacent short step-comments aren't flagged as one long one.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

MAX_LINES = 2
# A short leading label like "Arrange:"/"Act & assert:" -- capital start, colon within ~20
# chars, tight enough to not match an ordinary sentence with a colon further in.
LABEL_RE = re.compile(r"^[A-Z][\w\s+&]{0,18}:")


def staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [f for f in out.splitlines() if f]


def check(path: str, prefix: str) -> list[tuple[int, int, int]]:
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return []

    violations: list[tuple[int, int, int]] = []
    run: list[int] = []

    def flush() -> None:
        if len(run) > MAX_LINES:
            violations.append((run[0], run[-1], len(run)))

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith(prefix):
            text = stripped[len(prefix) :].strip()
            if run and LABEL_RE.match(text):
                flush()
                run = [i]
            else:
                run.append(i)
        else:
            flush()
            run = []
    flush()
    return violations


def prefix_for(path: str) -> str | None:
    if path.endswith(".py"):
        return "#"
    if path.endswith((".ts", ".tsx")):
        return "//"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", action="append", default=None, help="Check specific file(s) instead of staged files; always exits 0.")
    args = parser.parse_args()

    advisory = args.file is not None
    paths = args.file if advisory else staged_files()

    had_violation = False
    for path in paths:
        prefix = prefix_for(path)
        if prefix is None:
            continue
        for start, end, n in check(path, prefix):
            had_violation = True
            print(f"{path}:{start}-{end}: comment block is {n} lines (CODING_STANDARDS.md caps inline comments at {MAX_LINES})")

    if had_violation and not advisory:
        print("\nTrim the blocks above to 1-2 lines (see CODING_STANDARDS.md's Comments section).")
        print("To commit anyway: git commit --no-verify")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
