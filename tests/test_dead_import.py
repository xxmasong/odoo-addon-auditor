from odoo_auditor.findings import Severity
from odoo_auditor.rules.dead_import import check_source


def test_an_import_appended_to_a_comment_is_flagged():
    # The exact shape that aborted a real test run.
    source = "# tests for cheque printing from .common import TestChequeCommon\n"
    results = check_source(source, "tests/__init__.py")

    assert len(results) == 1
    assert results[0].severity is Severity.HIGH
    assert "never executes" in results[0].message
    assert "Failed to load registry" in results[0].remedy


def test_a_deliberately_commented_import_is_not_flagged():
    for source in (
        "# from .common import TestChequeCommon\n",
        "#import os\n",
        "    # from . import models\n",
    ):
        assert check_source(source, "m.py") == [], source


def test_a_real_import_is_not_flagged():
    source = "from .common import TestChequeCommon\nimport os\n"
    assert check_source(source, "m.py") == []


def test_a_trailing_comment_after_an_import_is_not_flagged():
    source = "from . import models  # noqa: F401\n"
    assert check_source(source, "m.py") == []


def test_a_prose_comment_without_an_import_is_not_flagged():
    source = "# this module imports nothing of note\n"
    assert check_source(source, "m.py") == []


def test_the_line_number_is_reported():
    source = "import os\n\n# see also from .common import Thing\n"
    assert check_source(source, "m.py")[0].line == 3
