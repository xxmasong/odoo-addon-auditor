from odoo_auditor.findings import Severity
from odoo_auditor.rules.missing_super import check_source


def findings_for(source: str):
    return check_source(source, "models/test.py")


class TestDetection:
    def test_override_without_super_on_an_inherited_model_is_critical(self):
        source = """
from odoo import models

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _prepare_invoice_line(self, **kwargs):
        return {"name": self.name}
"""
        results = findings_for(source)
        assert len(results) == 1
        assert results[0].severity is Severity.CRITICAL
        assert "_prepare_invoice_line" in results[0].message

    def test_override_with_super_is_clean(self):
        source = """
from odoo import models

class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def _prepare_invoice_line(self, **kwargs):
        values = super()._prepare_invoice_line(**kwargs)
        values["name"] = self.name
        return values
"""
        assert findings_for(source) == []

    def test_old_style_super_is_recognised(self):
        source = """
from odoo import models

class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        res = super(AccountMove, self).action_post()
        return res
"""
        assert findings_for(source) == []

    def test_a_new_model_is_only_medium(self):
        source = """
from odoo import models

class XenitReport(models.Model):
    _name = "xenit.report"

    def create(self, vals):
        return None
"""
        results = findings_for(source)
        assert len(results) == 1
        # Defining a new model without delegating is ordinary, not an incident.
        assert results[0].severity is Severity.MEDIUM

    def test_several_offending_methods_are_each_reported(self):
        source = """
from odoo import models

class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        pass

    def write(self, vals):
        pass

    def unlink(self):
        pass
"""
        results = findings_for(source)
        assert {f.message.split("overrides ")[1].split("(")[0] for f in results} == {
            "action_post",
            "write",
            "unlink",
        }

    def test_methods_outside_the_hook_list_are_ignored(self):
        source = """
from odoo import models

class SaleOrder(models.Model):
    _inherit = "sale.order"

    def my_custom_helper(self):
        return 42
"""
        assert findings_for(source) == []

    def test_a_plain_class_is_ignored(self):
        source = """
class NotAModel:
    def create(self, vals):
        return None
"""
        assert findings_for(source) == []

    def test_transient_and_abstract_models_are_covered(self):
        for base in ("TransientModel", "AbstractModel"):
            source = f"""
from odoo import models

class Wizard(models.{base}):
    _inherit = "some.wizard"

    def create(self, vals):
        return None
"""
            assert len(findings_for(source)) == 1, base

    def test_super_anywhere_in_the_body_counts(self):
        source = """
from odoo import models

class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        if self.state == "draft":
            return super().action_confirm()
        return False
"""
        # A conditional super() is not flagged: deciding whether every path
        # delegates is beyond what a static check should assert.
        assert findings_for(source) == []

    def test_the_finding_carries_a_line_and_snippet(self):
        source = """
from odoo import models

class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        return True
"""
        result = findings_for(source)[0]
        assert result.line == 7
        assert "def action_confirm" in result.snippet
        assert "super()" in result.remedy

    def test_a_syntax_error_is_reported_not_raised(self):
        results = findings_for("def broken(:\n    pass\n")
        assert len(results) == 1
        assert results[0].severity is Severity.INFO
        assert "could not be parsed" in results[0].message
