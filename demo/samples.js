// Sample addons for the playground.
//
// The "broken" sample reproduces the shape of a defect that took invoicing down
// on a live Odoo 18 database: an override of _prepare_invoice_line with no
// super() call, reading a field that Odoo 18 removed. The auditor was validated
// by pointing it back at the real module, which it flagged independently.

export const SAMPLES = {
  broken: {
    label: 'Broken addon (the real defect)',
    files: {
      '__manifest__.py': `{
    "name": "Product Combo Pack",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "license": "AGPL-3",
    "depends": ["sale_management", "account"],
    "installable": True,
}
`,
      'models/sale_order.py': `from odoo import api, fields, models


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    is_combo = fields.Boolean(string="Combo", track_visibility="onchange")

    def _prepare_invoice_line(self, **optional_values):
        # No super() call, and analytic_account_id was removed in Odoo 18.
        # This fires for EVERY order line, not just combo products.
        return {
            "display_type": self.display_type,
            "name": self.name,
            "product_id": self.product_id.id,
            "analytic_account_id": self.order_id.analytic_account_id.id,
        }

    @api.one
    def _compute_amount(self):
        self.price_subtotal = self.price_unit * self.product_uom_qty
`,
      'views/sale_order_views.xml': `<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_order_form_combo" model="ir.ui.view">
        <field name="model">sale.order</field>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='partner_id']" position="after">
                <field name="is_combo" attrs="{'invisible': [('state', '=', 'draft')]}"/>
                <field name="combo_note" states="draft,sent"/>
            </xpath>
        </field>
    </record>
</odoo>
`,
    },
  },

  clean: {
    label: 'Correct addon (must stay silent)',
    files: {
      '__manifest__.py': `{
    "name": "Sales Margin Notes",
    "version": "18.0.1.0.0",
    "category": "Sales",
    "license": "LGPL-3",
    "depends": ["sale_management"],
    "installable": True,
}
`,
      'models/sale_order.py': `from odoo import fields, models


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


class SalesSummary(models.Model):
    # A brand new model: not delegating create() here is ordinary, so the
    # auditor reports it at a lower severity than extending a core model.
    _name = "sales.summary"
    _description = "Sales summary"

    name = fields.Char(required=True)
`,
      'views/sale_order_views.xml': `<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="view_order_form_margin" model="ir.ui.view">
        <field name="model">sale.order</field>
        <field name="arch" type="xml">
            <xpath expr="//field[@name='partner_id']" position="after">
                <field name="margin_note" invisible="state == 'draft'"/>
            </xpath>
        </field>
    </record>
</odoo>
`,
    },
  },

  payment: {
    label: 'Silent payment failure',
    files: {
      '__manifest__.py': `{
    "name": "Account Payment Approval",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "depends": ["account"],
    "installable": True,
}
`,
      'models/account_payment.py': `from odoo import models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    def action_post(self):
        # No super(). With approval disabled this returns having done nothing,
        # so the payment silently never posts. It broke production with the
        # feature switched OFF.
        if self._check_payment_approval():
            self.move_id._post(soft=False)

    def _check_payment_approval(self):
        return self.env["ir.config_parameter"].sudo().get_param("approval_param")
`,
    },
  },

  owl: {
    label: 'Owl template (false-positive guard)',
    files: {
      '__manifest__.py': `{
    "name": "Owl Badge Widget",
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "installable": True,
}
`,
      'views/templates.xml': `<?xml version="1.0" encoding="utf-8"?>
<templates>
    <t t-name="owl_widget.Badge">
        <!-- t-att and t-attf are owl bindings, not the removed view attrs. -->
        <span t-att-class="props.className" t-esc="props.label"/>
        <div t-if="state.open" t-attf-style="width: {{props.width}}px">
            <t t-foreach="items" t-as="item" t-key="item.id">
                <span t-out="item.name"/>
            </t>
        </div>
    </t>
</templates>
`,
    },
  },
}
