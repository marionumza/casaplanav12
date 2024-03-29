# -*- coding: utf-8 -*-
# © 2009 Gabriel C. Stabel
# © 2009 Renato Lima (Akretion)
# © 2012 Raphaël Valyi (Akretion)
# © 2015  Michell Stuttgart (KMEE)
# © 2016 Danimar Ribeiro <danimaribeiro@gmail.com>, Trustcode
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).


import re
import base64
import logging

from odoo import models, fields, api, _
from odoo.addons.br_base.tools import fiscal
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    from pytrustnfe.nfe import consulta_cadastro
    from pytrustnfe.certificado import Certificado
except ImportError:
    _logger.error('Cannot import pytrustnfe', exc_info=True)


class ResPartner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner', 'br.localization.filtering']

    l10n_br_cnpj_cpf = fields.Char('CNPJ/CPF', size=18, copy=False,
                                   oldname='cnpj_cpf')
    l10n_br_inscr_est = fields.Char('State Inscription', size=16, copy=False,
                                    oldname='inscr_est')
    l10n_br_rg_fisica = fields.Char('RG', size=16, copy=False,
                                    oldname='rg_fisica')
    l10n_br_inscr_mun = fields.Char('Municipal Inscription', size=18,
                                    oldname='inscr_mun')
    l10n_br_suframa = fields.Char('Suframa', size=18, oldname='suframa')
    l10n_br_legal_name = fields.Char(
        'Legal Name', size=60, help="Name used in fiscal documents",
        oldname='legal_name')
    city_id = fields.Many2one(
        'res.city', 'City',
        domain="[('state_id','=',state_id)]")
    l10n_br_district = fields.Char('District', size=32, oldname='district')
    l10n_br_number = fields.Char(u'Number', size=10, oldname='number')

    _sql_constraints = [
        ('res_partner_l10n_br_cnpj_cpf_uniq', 'unique (l10n_br_cnpj_cpf)',
         _(u'This CPF/CNPJ number is already being used by another partner!'))
    ]

    @api.v8
    def _display_address(self, without_company=False):
        address = self

        if address.country_id and address.country_id.code != 'BR':
            # this ensure other localizations could do what they want
            return super(ResPartner, self)._display_address(without_company)
        else:
            address_format = (
                address.country_id and address.country_id.address_format or
                "%(street)s\n%(street2)s\n%(city)s %(state_code)s"
                "%(zip)s\n%(country_name)s")
            args = {
                'state_code': address.state_id and address.state_id.code or '',
                'state_name': address.state_id and address.state_id.name or '',
                'country_code': address.country_id and
                address.country_id.code or '',
                'country_name': address.country_id and
                address.country_id.name or '',
                'company_name': address.parent_id and
                address.parent_id.name or '',
                'city_name': address.city_id and
                address.city_id.name or '',
            }
            address_field = ['title', 'street', 'street2', 'zip', 'city',
                             'l10n_br_number', 'l10n_br_district']
            for field in address_field:
                args[field] = getattr(address, field) or ''
            if without_company:
                args['company_name'] = ''
            elif address.parent_id:
                address_format = '%(company_name)s\n' + address_format
            return address_format % args

    @api.multi
    @api.constrains('l10n_br_cnpj_cpf', 'country_id', 'is_company')
    def _check_cnpj_cpf(self):
        for item in self:
            country_code = item.country_id.code or ''
            if item.l10n_br_cnpj_cpf and country_code.upper() == 'BR':
                if item.is_company:
                    if not fiscal.validate_cnpj(item.l10n_br_cnpj_cpf):
                        raise UserError(_(u'Invalid CNPJ Number!'))
                elif not fiscal.validate_cpf(item.l10n_br_cnpj_cpf):
                    raise UserError(_(u'Invalid CPF Number!'))
        return True

    def _validate_ie_param(self, uf, inscr_est):
        try:
            mod = __import__(
                'odoo.addons.br_base.tools.fiscal', globals(),
                locals(), 'fiscal')

            validate = getattr(mod, 'validate_ie_%s' % uf)
            if not validate(inscr_est):
                return False
        except AttributeError:
            if not fiscal.validate_ie_param(uf, inscr_est):
                return False
        return True

    @api.depends('state_id', 'is_company')
    @api.constrains('l10n_br_inscr_est')
    def _check_ie(self):
        """Checks if company register number in field insc_est is valid,
        this method call others methods because this validation is State wise

        :Return: True or False."""
        if not self.l10n_br_inscr_est or self.l10n_br_inscr_est == 'ISENTO' \
                or not self.is_company:
            return True
        uf = self.state_id and self.state_id.code.lower() or ''
        res = self._validate_ie_param(uf, self.l10n_br_inscr_est)
        if not res:
            raise UserError(_(u'Invalid State Inscription!'))
        return True

    @api.one
    @api.constrains('l10n_br_inscr_est')
    def _check_ie_duplicated(self):
        """ Check if the field l10n_br_inscr_est has duplicated value
        """
        if not self.l10n_br_inscr_est or self.l10n_br_inscr_est == 'ISENTO':
            return True
        partner_ids = self.search(
            ['&', ('l10n_br_inscr_est', '=', self.l10n_br_inscr_est),
             ('id', '!=', self.id)])

        if len(partner_ids) > 0:
            raise UserError(_(u'This State Inscription/RG number '
                              u'is already being used by another partner!'))
        return True

    @api.onchange('l10n_br_cnpj_cpf')
    def _onchange_cnpj_cpf(self):
        country_code = self.country_id.code or ''
        if self.l10n_br_cnpj_cpf and country_code.upper() == 'BR':
            val = re.sub('[^0-9]', '', self.l10n_br_cnpj_cpf)
            if len(val) == 14:
                cnpj_cpf = "%s.%s.%s/%s-%s"\
                    % (val[0:2], val[2:5], val[5:8], val[8:12], val[12:14])
                self.l10n_br_cnpj_cpf = cnpj_cpf
            elif not self.is_company and len(val) == 11:
                cnpj_cpf = "%s.%s.%s-%s"\
                    % (val[0:3], val[3:6], val[6:9], val[9:11])
                self.l10n_br_cnpj_cpf = cnpj_cpf
            else:
                raise UserError(_(u'Verify CNPJ/CPF number'))

    @api.onchange('city_id')
    def _onchange_city_id(self):
        """ Ao alterar o campo city_id copia o nome
        do município para o campo city que é o campo nativo do módulo base
        para manter a compatibilidade entre os demais módulos que usam o
        campo city.
        """
        if self.city_id:
            self.city = self.city_id.name

    @api.onchange('zip')
    def onchange_mask_zip(self):
        if self.zip:
            val = re.sub('[^0-9]', '', self.zip)
            if len(val) == 8:
                zip = "%s-%s" % (val[0:5], val[5:8])
                self.zip = zip

    @api.model
    def _address_fields(self):
        """ Returns the list of address fields that are synced from the parent
        when the `use_parent_address` flag is set.
        Extenção para os novos campos do endereço """
        address_fields = super(ResPartner, self)._address_fields()
        return list(address_fields
                    + ['city_id', 'l10n_br_number', 'l10n_br_district'])

    @api.one
    def action_check_sefaz(self):
        if self.l10n_br_cnpj_cpf and self.state_id:
            if self.state_id.code == 'AL':
                raise UserError(_(u'Alagoas doesn\'t have this service'))
            if self.state_id.code == 'RJ':
                raise UserError(_(
                    u'Rio de Janeiro doesn\'t have this service'))
            company = self.env.user.company_id
            if (not company.l10n_br_nfe_a1_file
                    and not company.l10n_br_nfe_a1_password):
                raise UserError(_(
                    u'Configure the company\'s certificate and password'))
            cert = company.with_context(
                {'bin_size': False}).l10n_br_nfe_a1_file
            cert_pfx = base64.decodestring(cert)
            certificado = Certificado(cert_pfx,
                                      company.l10n_br_nfe_a1_password)
            cnpj = re.sub('[^0-9]', '', self.l10n_br_cnpj_cpf)
            obj = {'cnpj': cnpj, 'estado': self.state_id.code}
            resposta = consulta_cadastro(
                certificado, obj=obj, ambiente=1,
                estado=self.state_id.l10n_br_ibge_code)

            info = resposta['object'].getchildren()[0]
            info = info.infCons
            if info.cStat == 111 or info.cStat == 112:
                if not self.l10n_br_inscr_est:
                    self.l10n_br_inscr_est = info.infCad.IE.text
                if not self.l10n_br_cnpj_cpf:
                    self.l10n_br_cnpj_cpf = info.infCad.CNPJ.text

                def get_value(obj, prop):
                    if prop not in dir(obj):
                        return None
                    return getattr(obj, prop)
                self.l10n_br_legal_name = get_value(info.infCad, 'xNome')
                if "ender" not in dir(info.infCad):
                    return
                cep = get_value(info.infCad.ender, 'CEP') or ''
                self.zip = str(cep).zfill(8) if cep else ''
                self.street = get_value(info.infCad.ender, 'xLgr')
                self.l10n_br_number = get_value(info.infCad.ender, 'nro')
                self.street2 = get_value(info.infCad.ender, 'xCpl')
                self.l10n_br_district = get_value(info.infCad.ender, 'xBairro')
                cMun = get_value(info.infCad.ender, 'cMun')
                xMun = get_value(info.infCad.ender, 'xMun')
                city = None
                if cMun:
                    city = self.env['res.city'].search(
                        [('l10n_br_ibge_code', '=', str(cMun)[2:]),
                         ('state_id', '=', self.state_id.id)])
                if not city and xMun:
                    city = self.env['res.city'].search(
                        [('name', 'ilike', xMun),
                         ('state_id', '=', self.state_id.id)])
                if city:
                    self.city_id = city.id
            else:
                msg = "%s - %s" % (info.cStat, info.xMotivo)
                raise UserError(msg)
        else:
            raise UserError(_(u'Fill the State and CNPJ fields to search'))
