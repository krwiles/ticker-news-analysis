#!/usr/bin/env python3
"""Pre-commit check: flags inline comment blocks longer than 2 lines (CODING_STANDARDS.md's
"Comments" rule). Checks staged .py files (# comments) and staged .ts/.tsx files (// comments).
Docstrings/JSDoc are exempt -- that rule allows them more room.

A line starting a "Label:" pattern (e.g. "Arrange:", "Act & assert:") begins a fresh block even
with no blank line above it, so two adjacent short step-comments aren't flagged as one long one.
"""

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


def main() -> int:
    had_violation = False
    for path in staged_files():
        if path.endswith(".py"):
            prefix = "#"
        elif path.endswith((".ts", ".tsx")):
            prefix = "//"
        else:
            continue
        for start, end, n in check(path, prefix):
            had_violation = True
            print(f"{path}:{start}-{end}: comment block is {n} lines (CODING_STANDARDS.md caps inline comments at {MAX_LINES})")

    if had_violation:
        print("\nTrim the blocks above to 1-2 lines (see CODING_STANDARDS.md's Comments section).")
        print("To commit anyway: git commit --no-verify")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
