"""Detect overrides of core Odoo methods that never call ``super()``.

This is the highest-value check in the kit. Auditing a 743-module Odoo 18
database, two of the three modules that had to be removed shared exactly this
shape: a hook on a core model overridden without delegating upward, so the
addon's logic ran for *every* record rather than only its own.

The worst observed case overrode ``_prepare_invoice_line`` on ``sale.order.line``
and read ``analytic_account_id``, a field removed in Odoo 18. With no ``super()``
call and no guard it fired for every order line, which broke invoicing database
wide — not only for the products the addon was about.

Grep cannot answer this: finding ``def action_post`` is easy, but deciding whether
``super()`` is reached on every path needs the syntax tree.
"""

from __future__ import annotations

import ast
from pathlib import Path

from odoo_auditor.findings import Finding, Severity

#: Methods where skipping ``super()`` breaks records the addon does not own.
#: Chosen from what actually caused incidents, not from the whole ORM surface.
CRITICAL_HOOKS = {
    "create",
    "write",
    "unlink",
    "_prepare_invoice_line",
    "_prepare_invoice",
    "action_post",
    "_post",
    "action_confirm",
    "_action_confirm",
    "action_invoice_create",
    "_compute_amount",
    "copy",
    "default_get",
    "name_get",
    "_name_search",
    "read",
    "fields_get",
    "onchange",
}

RULE = "missing-super"


def _calls_super(node: ast.FunctionDef) -> bool:
    """True if the body contains a ``super()`` call anywhere."""
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue

        func = child.func
        # super().method(...)
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Call):
            inner = func.value.func
            if isinstance(inner, ast.Name) and inner.id == "super":
                return True
        # Bare super(...) — the Python 2 style still appears in older addons.
        if isinstance(func, ast.Name) and func.id == "super":
            return True
        # self._super or super(Model, self).method(...)
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id == "super":
                return True
    return False


def _is_odoo_model(node: ast.ClassDef) -> bool:
    """True if the class looks like an Odoo model.

    Checked by base class rather than by the presence of ``_inherit``, so that a
    model split across mixins is still considered.
    """
    for base in node.bases:
        if isinstance(base, ast.Attribute) and base.attr in {"Model", "TransientModel", "AbstractModel"}:
            return True
        if isinstance(base, ast.Name) and base.id in {"Model", "TransientModel", "AbstractModel"}:
            return True
    return False


def _inherits_existing_model(node: ast.ClassDef) -> bool:
    """True if the class sets ``_inherit``, meaning it extends an existing model.

    A class with only ``_name`` defines something new, where not calling
    ``super()`` on ``create`` is ordinary. Extending a core model is the risky
    case, so the severity differs.
    """
    for stmt in node.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for target in stmt.targets:
            if isinstance(target, ast.Name) and target.id == "_inherit":
                return True
    return False


def check_source(source: str, path: str) -> list[Finding]:
    """Audit one Python source string."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [
            Finding(
                rule=RULE,
                severity=Severity.INFO,
                path=path,
                line=exc.lineno or 0,
                message=f"could not be parsed: {exc.msg}",
                remedy="Check the file is valid Python for the target version.",
            )
        ]

    lines = source.splitlines()
    findings: list[Finding] = []

    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef) or not _is_odoo_model(cls):
            continue

        extends = _inherits_existing_model(cls)

        for stmt in cls.body:
            if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if stmt.name not in CRITICAL_HOOKS:
                continue
            if _calls_super(stmt):
                continue

            # A new model may legitimately not delegate; extending a core model
            # and not delegating is what broke production.
            severity = Severity.CRITICAL if extends else Severity.MEDIUM
            reason = (
                f"{cls.name} extends an existing model and overrides "
                f"{stmt.name}() without calling super()"
                if extends
                else f"{cls.name} defines {stmt.name}() without calling super()"
            )

            findings.append(
                Finding(
                    rule=RULE,
                    severity=severity,
                    path=path,
                    line=stmt.lineno,
                    message=reason,
                    remedy=(
                        f"Return super().{stmt.name}(...) on every path, or guard the "
                        f"custom branch so records this addon does not own are untouched."
                    ),
                    snippet=lines[stmt.lineno - 1].strip() if stmt.lineno <= len(lines) else "",
                )
            )

    return findings


def check_file(path: Path, *, root: Path | None = None) -> list[Finding]:
    display = str(path.relative_to(root)) if root else str(path)
    return check_source(path.read_text(encoding="utf-8", errors="replace"), display)
