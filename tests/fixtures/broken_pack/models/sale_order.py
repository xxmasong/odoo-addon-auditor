from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    is_combo = fields.Boolean(string="Combo", track_visibility="onchange")

    def _prepare_invoice_line(self, **optional_values):
        # Reproduces the shape of a real defect: no super() call, and a field
        # removed in Odoo 18 read unconditionally, so this fires for every
        # order line rather than only combo products.
        res = {
            "display_type": self.display_type,
            "name": self.name,
            "product_id": self.product_id.id,
            "analytic_account_id": self.order_id.analytic_account_id.id,
        }
        return res

    @api.one
    def _compute_amount(self):
        self.price_subtotal = self.price_unit * self.product_uom_qty
