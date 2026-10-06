from odoo_auditor.findings import Severity
from odoo_auditor.rules.removed_api import check_python_source, check_xml_source


class TestPython:
    def test_track_visibility_kwarg_is_flagged(self):
        source = """
from odoo import fields, models

class Partner(models.Model):
    _inherit = "res.partner"
    note = fields.Char(track_visibility="onchange")
"""
        results = check_python_source(source, "models/partner.py")
        assert any("track_visibility" in f.message for f in results)

    def test_digits_compute_is_flagged(self):
        source = """
from odoo import fields, models

class Line(models.Model):
    _name = "x.line"
    amount = fields.Float(digits_compute="Product Price")
"""
        assert any("digits_compute" in f.message for f in check_python_source(source, "m.py"))

    def test_analytic_account_id_access_is_critical(self):
        source = """
class Line:
    def build(self):
        return self.order_id.analytic_account_id.id
"""
        results = check_python_source(source, "models/line.py")
        assert results
        assert results[0].severity is Severity.CRITICAL
        assert "analytic_distribution" in results[0].remedy

    def test_api_one_decorator_is_flagged(self):
        source = """
from odoo import api, models

class Line(models.Model):
    _inherit = "x.line"

    @api.one
    def compute(self):
        pass
"""
        results = check_python_source(source, "m.py")
        assert any("@api.one" in f.message for f in results)

    def test_api_multi_decorator_is_flagged(self):
        source = """
from odoo import api, models

class Line(models.Model):
    _inherit = "x.line"

    @api.multi
    def compute(self):
        pass
"""
        assert any("@api.multi" in f.message for f in check_python_source(source, "m.py"))

    def test_api_depends_is_not_flagged(self):
        source = """
from odoo import api, fields, models

class Line(models.Model):
    _inherit = "x.line"
    total = fields.Float()

    @api.depends("price", "qty")
    def _compute_total(self):
        pass
"""
        assert check_python_source(source, "m.py") == []

    def test_modern_code_is_clean(self):
        source = """
from odoo import fields, models

class Partner(models.Model):
    _inherit = "res.partner"
    note = fields.Char(tracking=True)
    amount = fields.Float(digits=(16, 2))
"""
        assert check_python_source(source, "m.py") == []

    def test_a_syntax_error_yields_nothing(self):
        # missing_super reports the parse failure; this rule stays quiet.
        assert check_python_source("def (:", "m.py") == []


class TestXml:
    def test_attrs_attribute_is_flagged(self):
        xml = """<odoo>
    <field name="x" attrs="{'invisible': [('state', '=', 'draft')]}"/>
</odoo>"""
        results = check_xml_source(xml, "views/v.xml")
        assert len(results) == 1
        assert results[0].line == 2
        assert "attrs" in results[0].message

    def test_states_attribute_is_flagged(self):
        xml = """<odoo>
    <field name="x" states="draft,sent"/>
</odoo>"""
        assert len(check_xml_source(xml, "views/v.xml")) == 1

    def test_both_on_one_line_are_each_reported(self):
        xml = """<field name="x" attrs="{'invisible': []}" states="draft"/>"""
        assert len(check_xml_source(xml, "views/v.xml")) == 2

    def test_modern_inline_expressions_are_clean(self):
        xml = """<odoo>
    <field name="x" invisible="state == 'draft'" readonly="state != 'draft'"/>
</odoo>"""
        assert check_xml_source(xml, "views/v.xml") == []

    def test_owl_template_attributes_are_not_false_positives(self):
        # t-att/t-attf are owl bindings, not the removed view attributes.
        xml = """<templates>
    <t t-name="w.Badge">
        <span t-att-class="props.cls" t-esc="props.label"/>
        <div t-if="state.open" t-attf-style="width: {{w}}px"/>
    </t>
</templates>"""
        assert check_xml_source(xml, "static/src/t.xml") == []

    def test_a_line_mixing_owl_and_attrs_is_skipped(self):
        # Conservative: a QWeb line is not treated as a view definition.
        xml = """<t t-if="x"><field name="y" attrs="{'invisible': []}"/></t>"""
        assert check_xml_source(xml, "views/v.xml") == []
