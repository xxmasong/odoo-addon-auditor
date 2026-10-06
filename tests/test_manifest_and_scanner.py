from pathlib import Path

from odoo_auditor.findings import Severity
from odoo_auditor.rules.manifest import check_source
from odoo_auditor.scanner import audit_addon, audit_path, find_addons, is_addon

FIXTURES = Path(__file__).parent / "fixtures"


class TestManifest:
    def test_a_well_formed_manifest_is_clean(self):
        source = """
{
    "name": "Thing",
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
}
"""
        assert check_source(source, "__manifest__.py") == []

    def test_a_wrong_series_is_flagged(self):
        source = '{"name": "T", "version": "17.0.1.0.0", "license": "LGPL-3"}'
        results = check_source(source, "__manifest__.py")
        assert len(results) == 1
        # The manifest's claim is what every other tool trusts.
        assert "targets Odoo 17.0" in results[0].message

    def test_the_target_series_is_configurable(self):
        source = '{"name": "T", "version": "17.0.1.0.0", "license": "LGPL-3"}'
        assert check_source(source, "m.py", target_series="17.0") == []

    def test_a_version_without_a_series_is_flagged(self):
        source = '{"name": "T", "version": "1.0.0", "license": "LGPL-3"}'
        results = check_source(source, "m.py")
        assert any("omits the Odoo series" in f.message for f in results)

    def test_an_unparseable_version_is_flagged(self):
        source = '{"name": "T", "version": "latest", "license": "LGPL-3"}'
        assert any("not a recognised" in f.message for f in check_source(source, "m.py"))

    def test_missing_keys_are_flagged(self):
        results = check_source('{"version": "18.0.1.0.0"}', "m.py")
        messages = " ".join(f.message for f in results)
        assert "no 'name'" in messages
        assert "no 'license'" in messages

    def test_a_missing_name_is_critical(self):
        results = check_source('{"version": "18.0.1.0.0", "license": "LGPL-3"}', "m.py")
        assert results[0].severity is Severity.CRITICAL

    def test_an_unknown_licence_is_flagged(self):
        source = '{"name": "T", "version": "18.0.1.0.0", "license": "Beerware"}'
        assert any("not a licence Odoo recognises" in f.message for f in check_source(source, "m.py"))

    def test_auto_install_is_flagged(self):
        source = '{"name": "T", "version": "18.0.1.0.0", "license": "LGPL-3", "auto_install": True}'
        results = check_source(source, "m.py")
        assert any("auto_install" in f.message for f in results)

    def test_installable_false_is_info(self):
        source = (
            '{"name": "T", "version": "18.0.1.0.0", "license": "LGPL-3", "installable": False}'
        )
        results = check_source(source, "m.py")
        assert [f.severity for f in results] == [Severity.INFO]

    def test_a_broken_manifest_is_critical(self):
        results = check_source("{this is not python", "m.py")
        assert len(results) == 1
        assert results[0].severity is Severity.CRITICAL


class TestScanner:
    def test_is_addon(self):
        assert is_addon(FIXTURES / "clean_addon")
        assert not is_addon(FIXTURES)

    def test_find_addons_discovers_each_fixture(self):
        found = {p.name for p in find_addons(FIXTURES)}
        assert {"clean_addon", "broken_pack", "owl_template", "bad_manifest"} <= found

    def test_find_addons_on_an_addon_returns_itself(self):
        assert find_addons(FIXTURES / "clean_addon") == [FIXTURES / "clean_addon"]

    def test_the_clean_addon_has_no_findings(self):
        report = audit_addon(FIXTURES / "clean_addon")
        assert report.findings == []
        assert not report.blocking

    def test_the_broken_addon_is_blocking(self):
        report = audit_addon(FIXTURES / "broken_pack")

        assert report.blocking
        assert report.count(Severity.CRITICAL) >= 1

        rules = {f.rule for f in report.findings}
        assert "missing-super" in rules
        assert "removed-api" in rules

    def test_the_broken_addon_reproduces_the_real_defect(self):
        report = audit_addon(FIXTURES / "broken_pack")
        messages = " ".join(f.message for f in report.findings)

        # The two halves of the incident: no super(), plus a field 18 removed.
        assert "_prepare_invoice_line" in messages
        assert "analytic_account_id" in messages

    def test_the_broken_addon_flags_removed_xml_attributes(self):
        report = audit_addon(FIXTURES / "broken_pack")
        xml_findings = [f for f in report.findings if f.path.endswith(".xml")]
        assert len(xml_findings) == 2

    def test_an_owl_template_produces_no_false_positives(self):
        report = audit_addon(FIXTURES / "owl_template")
        assert report.findings == []

    def test_the_bad_manifest_fixture_is_flagged(self):
        report = audit_addon(FIXTURES / "bad_manifest")
        messages = " ".join(f.message for f in report.findings)
        assert "targets Odoo 17.0" in messages
        assert "Beerware" in messages
        assert "auto_install" in messages

    def test_findings_are_sorted_worst_first(self):
        report = audit_addon(FIXTURES / "broken_pack")
        ranks = [f.severity.rank for f in report.findings]
        assert ranks == sorted(ranks)

    def test_worst_reports_the_highest_severity(self):
        assert audit_addon(FIXTURES / "broken_pack").worst is Severity.CRITICAL
        assert audit_addon(FIXTURES / "clean_addon").worst is None

    def test_audit_path_covers_every_addon(self):
        reports = audit_path(FIXTURES)
        assert len(reports) >= 4
        assert any(r.blocking for r in reports)

    def test_paths_are_reported_relative_to_the_addon_parent(self):
        report = audit_addon(FIXTURES / "broken_pack")
        assert all(f.path.startswith("broken_pack/") for f in report.findings)
