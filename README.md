# odoo-addon-auditor

Static analysis for Odoo addons, built to answer one question before you install
third-party code into a production ERP: **will this break records it does not
own?**

```bash
pip install -e .
odoo-audit /opt/odoo/addons/some_module -v
```

## Why this exists

A manifest that says `18.0.1.0.0` is a claim, not a guarantee. Auditing a live
Odoo 18 database with 743 installed modules, three had to be removed because they
broke core flows — and all three were labelled for 18 while using APIs that 18 had
dropped. Each was found by hand, which took a day of test-restores and smoke runs.

This tool finds the same defects statically, in seconds, and was validated by
pointing it back at those modules:

| Module | How it broke production | Caught |
| --- | --- | --- |
| `product_combo_pack` | Overrode `_prepare_invoice_line` on `sale.order.line` with no `super()`, reading `analytic_account_id` (removed in 18). Broke **all** invoicing, for every order line. | ✅ 2 critical |
| `account_payment_approval` | Overrode `action_post()` with no `super()`. With the feature *switched off* the method did nothing and payments silently never posted. | ✅ 1 critical |
| `odoo_print_cheque` | An import glued onto the end of a comment line, so the name was never imported → `Failed to load registry`, aborting the **entire** test run. | ✅ 4 high |

### Against a real addon collection

Run over **737 third-party addons** from the Odoo apps store (the full
`apps-store` tree on that deployment):

| | |
| --- | --- |
| Addons scanned | 737 |
| Completely clean | 522 (71%) |
| Total findings | 269 |
| Addons with a **critical** finding | **20** |
| By severity | 38 critical, 97 high, 133 medium, 1 info |
| By rule | 122 manifest, 66 dead-import, 49 removed-api, 32 missing-super |

The 71% clean figure is the one that matters as much as the hits: a linter that
flags everything gets switched off, so the fixtures include an addon that must
stay silent and a QWeb template that must not false-positive.

## The checks

### `missing-super` — the highest-value rule

An override of a core ORM hook that never delegates upward. Two of the three
production incidents above were exactly this.

```python
# flagged: critical
class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"          # extends an existing model

    def _prepare_invoice_line(self, **kw):
        return {"name": self.name}        # no super() — runs for EVERY line
```

Grep finds `def action_post` easily; deciding whether `super()` is reached needs
the syntax tree, which is why this is an AST rule. It understands `super()`,
`super(Model, self)`, and a `super()` call anywhere in the body — a conditional
delegation is not flagged, because proving every path delegates is beyond what a
static check should assert.

Severity depends on `_inherit`: extending a core model and not delegating is
`critical`, while a brand-new model not calling `super().create()` is ordinary
and reported as `medium`.

### `removed-api`

APIs removed between Odoo 9 and 18, each either documented or hit during the real
migration: `analytic_account_id` on sale/purchase models (→ `analytic_distribution`),
`track_visibility` (→ `tracking`), `digits_compute` (→ `digits`), `@api.one`,
`@api.multi`, `oldname`, `get_object_reference`, and the `attrs=` / `states=` view
attributes dropped in 17.

Owl/QWeb templates are excluded, so `t-att`, `t-attf` and `t-if` do not produce
false positives — a real concern, since those appear in every modern addon's
static assets.

### `dead-import`

An import appended to the end of a comment line. It looks trivial and is not: it
is confined to `tests/`, costs nothing at runtime, and still aborts every other
module's test run through `Failed to load registry`. A line that is *only* a
commented-out import is deliberate and left alone.

### `manifest`

Series mismatch against the target (`--target`, default `18.0`), missing `name` /
`version` / `license`, unrecognised licences, and `auto_install` — which deserves
attention because such an addon installs itself into every database that satisfies
its dependencies, so a defect in it is not opt-in.

## Usage

```bash
odoo-audit path/to/addon                  # one addon
odoo-audit /opt/odoo/addons               # every addon beneath a directory
odoo-audit addons/ --target 17.0          # check against a different series
odoo-audit addons/ --json                 # machine-readable
odoo-audit addons/ --fail-on high         # tighten the exit-code gate
odoo-audit addons/ -v                     # include remedies
```

Exit codes: `0` nothing at or above the gate, `1` findings at the gate (default
`critical`), `2` the path does not exist or holds no addon. That makes it usable
as a CI gate or a pre-install hook:

```yaml
- run: odoo-audit addons/ --fail-on critical
```

```
broken_pack (3 critical, 4 high)
  critical  broken_pack/models/sale_order.py:9  SaleOrderLine extends an existing
            model and overrides _prepare_invoice_line() without calling super()
            │ def _prepare_invoice_line(self, **optional_values):
            └ Return super()._prepare_invoice_line(...) on every path, or guard the
              custom branch so records this addon does not own are untouched.
```

## Tests

```bash
python -m pytest tests/ -q      # 65 tests
```

The fixtures under `tests/fixtures/` reproduce the real defects: `broken_pack`
mirrors the invoicing incident, `owl_template` guards against the QWeb false
positive, and `clean_addon` must stay silent — a linter that cries wolf on correct
code gets switched off.

## Layout

```
odoo_auditor/
  findings.py              Finding and Severity
  scanner.py               addon discovery and rule dispatch
  cli.py                   argument parsing, rendering, exit codes
  rules/
    missing_super.py       AST: core hooks overridden without super()
    removed_api.py         AST + XML: APIs removed in 9–18
    dead_import.py         imports swallowed by a comment
    manifest.py            version, licence and install flags
tests/
  fixtures/                addons reproducing the real defects
```

## Known limits

- **Static only.** It cannot know whether a `super()` call is reached on every
  branch, nor catch defects that only appear against real data. It narrows what
  needs a test-restore; it does not replace one.
- `analytic_account_id` is flagged on any attribute access, since inferring the
  model of `self.order_id` would need full type resolution. On a model where the
  field still exists this is a false positive.
- The removed-API list is curated, not exhaustive. It covers what caused real
  incidents rather than every entry in the migration guide.
- No check of `security/ir.model.access.csv`, view XML validity, or dependency
  cycles.
- Python 3.10+, because the rules use modern `ast` and `match`-era syntax.

## Licence

MIT

## Live playground

<https://auditor.xenitsystems.com>

The page runs **this package** in the browser under Pyodide — not a
reimplementation — so the findings it reports are the findings the CLI reports.
Four samples are preloaded, including the real production defect and two that
must stay silent (a correct addon and an Owl template), because a linter has to
be right about clean code as often as it catches bad code.

Rebuild the browser bundle after changing a rule:

```bash
python demo/build.py        # regenerates demo/auditor-src.js from odoo_auditor/
```

The demo is deployed as a static container behind Traefik; see `demo/compose.yml`.
