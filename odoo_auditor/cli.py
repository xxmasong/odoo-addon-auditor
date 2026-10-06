"""Command line entry point.

    odoo-audit /opt/odoo/addons/some_module
    odoo-audit /opt/odoo/addons --json
    odoo-audit /opt/odoo/addons --fail-on high
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from odoo_auditor.findings import Severity
from odoo_auditor.scanner import AddonReport, audit_path

_COLOUR = {
    Severity.CRITICAL: "\033[1;31m",
    Severity.HIGH: "\033[31m",
    Severity.MEDIUM: "\033[33m",
    Severity.INFO: "\033[36m",
}
_RESET = "\033[0m"


def _render(reports: list[AddonReport], *, use_colour: bool, verbose: bool) -> str:
    out: list[str] = []

    for report in reports:
        if not report.findings:
            out.append(f"{report.name}: clean")
            continue

        counts = ", ".join(
            f"{report.count(s)} {s.value}" for s in Severity if report.count(s)
        )
        out.append(f"\n{report.name} ({counts})")

        for finding in report.findings:
            tint = _COLOUR[finding.severity] if use_colour else ""
            reset = _RESET if use_colour else ""
            label = f"{tint}{finding.severity.value:>8}{reset}"
            out.append(f"  {label}  {finding.path}:{finding.line}  {finding.message}")
            if finding.snippet:
                out.append(f"            │ {finding.snippet}")
            if verbose and finding.remedy:
                out.append(f"            └ {finding.remedy}")

    total = sum(len(r.findings) for r in reports)
    blocking = sum(1 for r in reports if r.blocking)
    out.append(
        f"\n{len(reports)} addon(s), {total} finding(s), "
        f"{blocking} with a critical finding"
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="odoo-audit",
        description=(
            "Audit Odoo addons for version-compatibility defects before installing "
            "them, in particular overrides of core methods that never call super()."
        ),
    )
    parser.add_argument("path", type=Path, help="an addon directory, or a directory of addons")
    parser.add_argument(
        "--target", default="18.0", metavar="SERIES", help="Odoo series to check against"
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    parser.add_argument(
        "--fail-on",
        choices=[s.value for s in Severity],
        default="critical",
        help="exit non-zero when a finding of this severity or worse is present",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="include remedies")
    parser.add_argument("--no-colour", action="store_true", help="disable colour")
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"odoo-audit: {args.path} does not exist", file=sys.stderr)
        return 2

    reports = audit_path(args.path, target_series=args.target)

    if not reports:
        print(f"odoo-audit: no addon found under {args.path}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "addon": r.name,
                        "path": str(r.path),
                        "findings": [f.as_dict() for f in r.findings],
                    }
                    for r in reports
                ],
                indent=2,
            )
        )
    else:
        use_colour = not args.no_colour and sys.stdout.isatty()
        print(_render(reports, use_colour=use_colour, verbose=args.verbose))

    threshold = Severity(args.fail_on)
    worst = min(
        (f.severity for r in reports for f in r.findings),
        key=lambda s: s.rank,
        default=None,
    )
    if worst is not None and worst.rank <= threshold.rank:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
