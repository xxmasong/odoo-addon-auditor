"""Flag APIs removed or renamed in Odoo 15–18.

Every entry here was either hit during a real migration audit or is a documented
removal. The point of the rule is that a module labelled ``18.0.x`` may still be
Odoo 17-era code: the manifest version is a claim, not a guarantee, and all three
modules that had to be removed from the database this was built against were
labelled for 18 while using APIs that 18 had dropped.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

from odoo_auditor.findings import Finding, Severity

RULE = "removed-api"


@dataclass(frozen=True)
class Removal:
    name: str
    removed_in: str
    replacement: str
    severity: Severity
    #: Restrict the finding to these models, where the removal was model specific.
    models: tuple[str, ...] = ()


PYTHON_REMOVALS: dict[str, Removal] = {
    "analytic_account_id": Removal(
        name="analytic_account_id",
        removed_in="18.0",
        replacement="analytic_distribution",
        severity=Severity.CRITICAL,
        models=("sale.order", "sale.order.line", "purchase.order"),
    ),
    "track_visibility": Removal(
        name="track_visibility",
        removed_in="12.0",
        replacement="tracking=True on the field",
        severity=Severity.HIGH,
    ),
    "digits_compute": Removal(
        name="digits_compute",
        removed_in="9.0",
        replacement="digits=",
        severity=Severity.HIGH,
    ),
    "oldname": Removal(
        name="oldname",
        removed_in="13.0",
        replacement="a migration script",
        severity=Severity.MEDIUM,
    ),
    "get_object_reference": Removal(
        name="get_object_reference",
        removed_in="15.0",
        replacement="env.ref() or _xmlid_lookup",
        severity=Severity.MEDIUM,
    ),
}

DECORATOR_REMOVALS: dict[str, Removal] = {
    "one": Removal(
        name="@api.one",
        removed_in="12.0",
        replacement="operate on self, or use ensure_one()",
        severity=Severity.HIGH,
    ),
    "multi": Removal(
        name="@api.multi",
        removed_in="13.0",
        replacement="nothing; it is the default",
        severity=Severity.MEDIUM,
    ),
    "returns": Removal(
        name="@api.returns",
        removed_in="",
        replacement="",
        severity=Severity.INFO,
    ),
    "cr_uid_context": Removal(
        name="@api.cr_uid_context",
        removed_in="10.0",
        replacement="the new-style API",
        severity=Severity.HIGH,
    ),
}

#: XML view attributes removed in Odoo 17 in favour of inline Python expressions.
XML_REMOVALS = {
    "attrs": Removal(
        name="attrs",
        removed_in="17.0",
        replacement='invisible="...", readonly="..." or required="..." directly',
        severity=Severity.HIGH,
    ),
    "states": Removal(
        name="states",
        removed_in="17.0",
        replacement='invisible="state not in (...)"',
        severity=Severity.HIGH,
    ),
}

_XML_ATTR = re.compile(r"\b(attrs|states)\s*=\s*[\"']")
# JS templates (owl) legitimately use t-attf and similar; only flag real view XML.
_JS_TEMPLATE_HINT = re.compile(r"\bt-(att|attf|if|esc|out|foreach)\b")


def check_python_source(source: str, path: str) -> list[Finding]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # missing_super reports the parse failure; do not duplicate it.
        return []

    lines = source.splitlines()
    findings: list[Finding] = []

    def snippet(line: int) -> str:
        return lines[line - 1].strip() if 0 < line <= len(lines) else ""

    for node in ast.walk(tree):
        # Removed keyword arguments on field definitions.
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg and kw.arg in PYTHON_REMOVALS:
                    removal = PYTHON_REMOVALS[kw.arg]
                    findings.append(
                        Finding(
                            rule=RULE,
                            severity=removal.severity,
                            path=path,
                            line=node.lineno,
                            message=(
                                f"{removal.name} was removed in Odoo {removal.removed_in}"
                            ),
                            remedy=f"Use {removal.replacement}.",
                            snippet=snippet(node.lineno),
                        )
                    )

        # Removed decorators.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "api"
                    and target.attr in DECORATOR_REMOVALS
                ):
                    removal = DECORATOR_REMOVALS[target.attr]
                    if removal.severity is Severity.INFO:
                        continue
                    findings.append(
                        Finding(
                            rule=RULE,
                            severity=removal.severity,
                            path=path,
                            line=decorator.lineno,
                            message=f"{removal.name} was removed in Odoo {removal.removed_in}",
                            remedy=f"Replace with {removal.replacement}.",
                            snippet=snippet(decorator.lineno),
                        )
                    )

        # Attribute access to a field removed on specific models.
        if isinstance(node, ast.Attribute) and node.attr in PYTHON_REMOVALS:
            removal = PYTHON_REMOVALS[node.attr]
            if not removal.models:
                continue
            findings.append(
                Finding(
                    rule=RULE,
                    severity=removal.severity,
                    path=path,
                    line=node.lineno,
                    message=(
                        f"{removal.name} was removed in Odoo {removal.removed_in} on "
                        f"{', '.join(removal.models)}"
                    ),
                    remedy=(
                        f"Use {removal.replacement}. If the attribute belongs to a "
                        f"different model, confirm which and silence this finding."
                    ),
                    snippet=snippet(node.lineno),
                )
            )

    return findings


def check_xml_source(source: str, path: str) -> list[Finding]:
    findings: list[Finding] = []

    for number, line in enumerate(source.splitlines(), start=1):
        if _JS_TEMPLATE_HINT.search(line):
            # An owl/QWeb template, where these attributes are not the removed ones.
            continue
        for match in _XML_ATTR.finditer(line):
            removal = XML_REMOVALS[match.group(1)]
            findings.append(
                Finding(
                    rule=RULE,
                    severity=removal.severity,
                    path=path,
                    line=number,
                    message=f'{removal.name}="..." was removed in Odoo {removal.removed_in}',
                    remedy=f"Use {removal.replacement}.",
                    snippet=line.strip(),
                )
            )

    return findings


def check_file(path: Path, *, root: Path | None = None) -> list[Finding]:
    display = str(path.relative_to(root)) if root else str(path)
    text = path.read_text(encoding="utf-8", errors="replace")

    if path.suffix == ".py":
        return check_python_source(text, display)
    if path.suffix == ".xml":
        return check_xml_source(text, display)
    return []
