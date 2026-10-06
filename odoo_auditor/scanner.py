"""Walk an addon tree and collect findings from every rule."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from odoo_auditor.findings import Finding, Severity
from odoo_auditor.rules import dead_import, manifest, missing_super, removed_api

#: Directories that never contain addon source worth auditing.
SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "static",  # compiled JS and vendored libraries
    "tests.disabled",
    ".mypy_cache",
    ".ruff_cache",
}


@dataclass
class AddonReport:
    name: str
    path: Path
    findings: list[Finding] = field(default_factory=list)

    @property
    def worst(self) -> Severity | None:
        return min((f.severity for f in self.findings), key=lambda s: s.rank, default=None)

    def count(self, severity: Severity) -> int:
        return sum(1 for f in self.findings if f.severity is severity)

    @property
    def blocking(self) -> bool:
        """True if installing this addon risks breaking records it does not own."""
        return self.count(Severity.CRITICAL) > 0


def is_addon(path: Path) -> bool:
    return (path / "__manifest__.py").is_file()


def find_addons(root: Path) -> list[Path]:
    """Locate addon directories under ``root``, including ``root`` itself."""
    if is_addon(root):
        return [root]

    found: list[Path] = []
    for candidate in sorted(root.rglob("__manifest__.py")):
        if any(part in SKIP_DIRS for part in candidate.parts):
            continue
        found.append(candidate.parent)
    return found


def _source_files(addon: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(addon.rglob("*")):
        if not path.is_file() or path.suffix not in {".py", ".xml"}:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(addon).parts):
            continue
        files.append(path)
    return files


def audit_addon(addon: Path, *, target_series: str = "18.0") -> AddonReport:
    report = AddonReport(name=addon.name, path=addon)
    root = addon.parent

    manifest_path = addon / "__manifest__.py"
    if manifest_path.is_file():
        report.findings.extend(
            manifest.check_file(manifest_path, root=root, target_series=target_series)
        )

    for path in _source_files(addon):
        if path.name == "__manifest__.py":
            continue
        if path.suffix == ".py":
            report.findings.extend(missing_super.check_file(path, root=root))
            report.findings.extend(dead_import.check_file(path, root=root))
        report.findings.extend(removed_api.check_file(path, root=root))

    report.findings.sort(key=lambda f: (f.severity.rank, f.path, f.line))
    return report


def audit_path(root: Path, *, target_series: str = "18.0") -> list[AddonReport]:
    return [audit_addon(addon, target_series=target_series) for addon in find_addons(root)]
