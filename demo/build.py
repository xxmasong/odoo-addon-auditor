#!/usr/bin/env python3
"""Bundle the auditor package into a JS module for the browser playground.

The playground runs the real package under Pyodide rather than reimplementing
the rules in JavaScript, so what the page reports is what the CLI reports. That
only works because the package is pure standard library; a C extension would
need a compiled wheel.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> int:
    package = ROOT / "odoo_auditor"
    if not package.is_dir():
        print("cannot find odoo_auditor/", file=sys.stderr)
        return 1

    sources = {
        str(path.relative_to(ROOT)): path.read_text(encoding="utf-8")
        for path in sorted(package.rglob("*.py"))
    }

    target = ROOT / "demo" / "auditor-src.js"
    target.write_text(
        "// Generated from odoo_auditor/ by demo/build.py — do not edit by hand.\n"
        f"export const AUDITOR_SOURCES = {json.dumps(sources, indent=2)};\n",
        encoding="utf-8",
    )
    print(f"bundled {len(sources)} modules into {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
