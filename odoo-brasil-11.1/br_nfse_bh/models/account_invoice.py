# © 2018 Danimar Ribeiro, Trustcode
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).


from odoo import models


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    def _return_pdf_invoice(self, doc):
        if doc.model == '014':  # Nota Belo Horizonte
            return 'br_nfse_bh.report_br_nfse_danfe_bh'
        return super(AccountInvoice, self)._return_pdf_invoice(doc)

    def _prepare_edoc_item_vals(self, line):
        res = super(AccountInvoice, self)._prepare_edoc_item_vals(line)
        res['codigo_tributacao_municipio'] = \
            line.l10n_br_service_type_id.codigo_tributacao_municipio
        return res
