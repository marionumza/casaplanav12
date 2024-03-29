# -*- coding: utf-8 -*-
# © 2016 Danimar Ribeiro, Trustcode
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import api, fields, models


class AccountInvoice(models.Model):
    _name = 'account.invoice'
    _inherit = ['account.invoice', 'br.localization.filtering']

    @api.depends('l10n_br_invoice_eletronic_ids.numero_nfse')
    def _compute_nfse_number(self):
        for inv in self:
            numeros = inv.l10n_br_invoice_eletronic_ids.mapped('numero_nfse')
            numeros = [n for n in numeros if n]
            inv.l10n_br_numero_nfse = ','.join(numeros)

    l10n_br_ambiente_nfse = fields.Selection(
        string="Ambiente NFe", related="company_id.l10n_br_tipo_ambiente_nfse",
        readonly=True, oldname='ambiente_nfse')
    l10n_br_nfse_eletronic = fields.Boolean(
        related="l10n_br_service_document_id.nfse_eletronic", readonly=True,
        oldname='nfse_eletronic')
    l10n_br_numero_nfse = fields.Char(
        'NFS-e', size=30, compute='_compute_nfse_number', store=True,
        oldname='numero_nfse')

    def _prepare_edoc_vals(self, inv, inv_lines, serie_id):
        res = super(AccountInvoice, self)._prepare_edoc_vals(
            inv, inv_lines, serie_id)
        res['nfse_eletronic'] = inv.l10n_br_nfse_eletronic
        res['ambiente'] = inv.l10n_br_ambiente_nfse
        res['serie'] = serie_id.id
        res['serie_documento'] = serie_id.code
        res['model'] = serie_id.fiscal_document_id.code
        # Feito para evitar que o número seja incrementado duas vezes
        if 'numero' not in res:
            res['numero'] = serie_id.internal_sequence_id.next_by_id()
        return res


class AccountInvoiceLine(models.Model):
    _name = 'account.invoice.line'
    _inherit = ['account.invoice.line', 'br.localization.filtering']

    l10n_br_numero_nfse = fields.Char(
        string="Número NFS-e",
        help="""Número da NFS-e na qual o item foi \
        transmitido eletrônicamente.""",
        oldname='numero_nfse')
