from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    margin_note = fields.Char(string="Margin note")

    def _prepare_invoice_line(self, **optional_values):
        values = super()._prepare_invoice_line(**optional_values)
        if self.margin_note:
            values["name"] = f"{values.get('name', '')} ({self.margin_note})"
        return values

    def create(self, vals_list):
        records = super().create(vals_list)
        records._recompute_notes()
        return records

    def _recompute_notes(self):
        for record in self:
            record.margin_note = record.margin_note or ""


class SaleOrderReport(models.Model):
    # A brand new model: not calling super() on create would be ordinary here.
    _name = "xenit.sale.summary"
    _description = "Sales summary"

    name = fields.Char(required=True)
