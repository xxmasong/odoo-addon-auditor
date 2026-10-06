"""Audit ``__manifest__.py``.

The version string is the main thing worth checking, because it is the claim
every other tool trusts. An addon declaring ``18.0.1.0.0`` while using Odoo
17 APIs installs without complaint and fails at runtime, which is precisely how
three modules reached a production database before being removed.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from odoo_auditor.findings import Finding, Severity

RULE = "manifest"

# Odoo's convention: <odoo series>.<module major>.<minor>.<patch>
_VERSION = re.compile(r"^(?P<series>\d+\.\d+)\.(?P<rest>\d+\.\d+\.\d+)$")
_SHORT_VERSION = re.compile(r"^\d+\.\d+\.\d+$")

REQUIRED_KEYS = ("name", "version", "license")
KNOWN_LICENSES = {
    "LGPL-3",
    "AGPL-3",
    "GPL-3",
    "GPL-3 or any later version",
    "OPL-1",
    "OEEL-1",
    "Other proprietary",
    "Other OSI approved licence",
}


def _literal(node: ast.expr):
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def check_source(source: str, path: str, *, target_series: str = "18.0") -> list[Finding]:
    findings: list[Finding] = []

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [
            Finding(
                rule=RULE,
                severity=Severity.CRITICAL,
                path=path,
                line=exc.lineno or 0,
                message=f"the manifest is not valid Python: {exc.msg}",
                remedy="A manifest must be a single dict literal.",
            )
        ]

    manifest: dict | None = None
    manifest_line = 1
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            value = _literal(node)
            if isinstance(value, dict):
                manifest = value
                manifest_line = node.lineno
                break

    if manifest is None:
        return [
            Finding(
                rule=RULE,
                severity=Severity.CRITICAL,
                path=path,
                line=1,
                message="no dict literal found in the manifest",
                remedy="The manifest must evaluate to a dict.",
            )
        ]

    for key in REQUIRED_KEYS:
        if key not in manifest:
            findings.append(
                Finding(
                    rule=RULE,
                    severity=Severity.HIGH if key != "name" else Severity.CRITICAL,
                    path=path,
                    line=manifest_line,
                    message=f"the manifest has no '{key}'",
                    remedy=f"Add a '{key}' entry.",
                )
            )

    version = manifest.get("version")
    if isinstance(version, str):
        match = _VERSION.match(version)
        if match:
            series = match.group("series")
            if series != target_series:
                findings.append(
                    Finding(
                        rule=RULE,
                        severity=Severity.HIGH,
                        path=path,
                        line=manifest_line,
                        message=(
                            f"version '{version}' targets Odoo {series}, "
                            f"not {target_series}"
                        ),
                        remedy=f"Confirm compatibility, then set the series to {target_series}.",
                    )
                )
        elif _SHORT_VERSION.match(version):
            findings.append(
                Finding(
                    rule=RULE,
                    severity=Severity.MEDIUM,
                    path=path,
                    line=manifest_line,
                    message=f"version '{version}' omits the Odoo series",
                    remedy=f"Use the full form, e.g. {target_series}.{version}.",
                )
            )
        else:
            findings.append(
                Finding(
                    rule=RULE,
                    severity=Severity.MEDIUM,
                    path=path,
                    line=manifest_line,
                    message=f"version '{version}' is not a recognised Odoo version",
                    remedy=f"Use <series>.<major>.<minor>.<patch>, e.g. {target_series}.1.0.0.",
                )
            )

    licence = manifest.get("license")
    if isinstance(licence, str) and licence not in KNOWN_LICENSES:
        findings.append(
            Finding(
                rule=RULE,
                severity=Severity.MEDIUM,
                path=path,
                line=manifest_line,
                message=f"'{licence}' is not a licence Odoo recognises",
                remedy=f"Use one of: {', '.join(sorted(KNOWN_LICENSES))}.",
            )
        )

    if manifest.get("installable") is False:
        findings.append(
            Finding(
                rule=RULE,
                severity=Severity.INFO,
                path=path,
                line=manifest_line,
                message="the addon is marked installable=False",
                remedy="It will not appear in the apps list.",
            )
        )

    # An addon that auto-installs itself enters every database that satisfies its
    # dependencies, so a defect in it is not opt-in.
    if manifest.get("auto_install"):
        findings.append(
            Finding(
                rule=RULE,
                severity=Severity.MEDIUM,
                path=path,
                line=manifest_line,
                message="auto_install is set, so this addon installs itself automatically",
                remedy="Confirm that is intended; a defect here affects every database.",
            )
        )

    return findings


def check_file(path: Path, *, root: Path | None = None, target_series: str = "18.0") -> list[Finding]:
    display = str(path.relative_to(root)) if root else str(path)
    return check_source(
        path.read_text(encoding="utf-8", errors="replace"),
        display,
        target_series=target_series,
    )
