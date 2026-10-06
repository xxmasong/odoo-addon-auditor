"""Detect imports that are silently inert because they sit inside a comment.

This looks like a triviality and is not. An addon audited on a real deployment
had, in ``tests/__init__.py``:

    # from .common import TestChequeCommon  <- appended to a comment line

Python read the whole line as a comment, the name was never imported, and the
test module referencing it raised ``NameError`` at import time. Odoo surfaces
that as ``Failed to load registry``, which **aborted the entire test run** for
every other module in the batch — far more disruptive than one broken addon.

The rule looks for an import statement that trails other content on a commented
line, which is the shape that hides it from both the reader and the parser.
"""

from __future__ import annotations

import re
from pathlib import Path

from odoo_auditor.findings import Finding, Severity

RULE = "dead-import"

# A comment line whose text contains an import *after* some other prose, e.g.
#   "# needed for the suite from .common import X"
# A line that is only a commented-out import is deliberate and not flagged.
_COMMENTED_IMPORT = re.compile(
    r"^\s*#\s*(?P<prefix>.*\S)\s+(?P<stmt>(?:from\s+\S+\s+import|import)\s+\S+)"
)
# A line that is purely a commented import, which is normal practice.
_BARE_COMMENTED_IMPORT = re.compile(r"^\s*#\s*(?:from\s+\S+\s+)?import\s")


def check_source(source: str, path: str) -> list[Finding]:
    findings: list[Finding] = []

    for number, line in enumerate(source.splitlines(), start=1):
        if "import" not in line or "#" not in line:
            continue
        if _BARE_COMMENTED_IMPORT.match(line):
            # Intentionally disabled, not accidentally swallowed.
            continue

        match = _COMMENTED_IMPORT.match(line)
        if not match:
            continue

        findings.append(
            Finding(
                rule=RULE,
                severity=Severity.HIGH,
                path=path,
                line=number,
                message=(
                    "an import statement is appended to a comment, so it never executes"
                ),
                remedy=(
                    "Move the import onto its own line. In a tests/__init__.py this "
                    "raises NameError at import time, which Odoo reports as "
                    "'Failed to load registry' and aborts the whole test run."
                ),
                snippet=line.strip(),
            )
        )

    return findings


def check_file(path: Path, *, root: Path | None = None) -> list[Finding]:
    display = str(path.relative_to(root)) if root else str(path)
    return check_source(path.read_text(encoding="utf-8", errors="replace"), display)
