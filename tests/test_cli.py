import json
from pathlib import Path

from odoo_auditor.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_a_clean_addon_exits_zero(capsys):
    code = main([str(FIXTURES / "clean_addon"), "--no-colour"])
    assert code == 0
    assert "clean" in capsys.readouterr().out


def test_a_blocking_addon_exits_one(capsys):
    code = main([str(FIXTURES / "broken_pack"), "--no-colour"])
    assert code == 1
    out = capsys.readouterr().out
    assert "critical" in out
    assert "_prepare_invoice_line" in out


def test_a_missing_path_exits_two(capsys):
    assert main([str(FIXTURES / "does_not_exist")]) == 2
    assert "does not exist" in capsys.readouterr().err


def test_a_directory_with_no_addon_exits_two(tmp_path, capsys):
    assert main([str(tmp_path)]) == 2
    assert "no addon found" in capsys.readouterr().err


def test_json_output_is_valid(capsys):
    main([str(FIXTURES / "broken_pack"), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert payload[0]["addon"] == "broken_pack"
    assert payload[0]["findings"]
    assert {"rule", "severity", "path", "line", "message"} <= set(payload[0]["findings"][0])


def test_fail_on_can_be_relaxed(capsys):
    # bad_manifest's worst finding is HIGH, so a critical gate passes it.
    assert main([str(FIXTURES / "bad_manifest"), "--no-colour"]) == 0
    capsys.readouterr()
    assert main([str(FIXTURES / "bad_manifest"), "--fail-on", "high", "--no-colour"]) == 1


def test_fail_on_info_catches_everything(capsys):
    assert main([str(FIXTURES / "bad_manifest"), "--fail-on", "info", "--no-colour"]) == 1
    capsys.readouterr()


def test_verbose_includes_remedies(capsys):
    main([str(FIXTURES / "broken_pack"), "--no-colour", "-v"])
    assert "super()" in capsys.readouterr().out


def test_the_target_series_is_honoured(capsys):
    main([str(FIXTURES / "bad_manifest"), "--target", "17.0", "--no-colour"])
    assert "targets Odoo 17.0" not in capsys.readouterr().out


def test_scanning_a_tree_summarises_every_addon(capsys):
    main([str(FIXTURES), "--no-colour"])
    out = capsys.readouterr().out
    assert "addon(s)" in out
    assert "finding(s)" in out
