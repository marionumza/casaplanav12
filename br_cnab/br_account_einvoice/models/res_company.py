# -*- coding: utf-8 -*-
# © 2016 Danimar Ribeiro <danimaribeiro@gmail.com>, Trustcode
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_br_nfse_conjugada = fields.Boolean(
        string="Emite NFSe Conjugada?", default=False)

    l10n_br_tipo_ambiente_nfse = fields.Selection(
        [('producao', u'Produção'), ('homologacao', u'Homologação')],
        string="Ambiente NFSe", default='homologacao',
        oldname='tipo_ambiente_nfse')

    l10n_br_nfe_email_template = fields.Many2one(
        'mail.template', string="Template de Email para NFe",
        oldname='nfe_email_template')
