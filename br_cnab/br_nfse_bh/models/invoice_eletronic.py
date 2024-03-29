# © 2018 Danimar Ribeiro <danimaribeiro@gmail.com>, Trustcode
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import re
import base64
import pytz
import time
import logging
from datetime import datetime
from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval
from odoo.exceptions import UserError

from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT as DTFT

_logger = logging.getLogger(__name__)

try:
    from pytrustnfe.nfse.bh import xml_gerar_nfse
    from pytrustnfe.nfse.bh import gerar_nfse
    from pytrustnfe.nfse.bh import cancelar_nfse

    from pytrustnfe.certificado import Certificado
except ImportError:
    _logger.error('Cannot import pytrustnfe', exc_info=True)


STATE = {'edit': [('readonly', False)]}


class InvoiceEletronicItem(models.Model):
    _inherit = 'invoice.eletronic.item'

    codigo_tributacao_municipio = fields.Char(
        string=u"Cód. Tribut. Munic.", size=20, readonly=True,
        help="Código de Tributação no Munípio", states=STATE)


class InvoiceEletronic(models.Model):
    _inherit = 'invoice.eletronic'

    @api.depends('valor_retencao_pis', 'valor_retencao_cofins',
                 'valor_retencao_irrf', 'valor_retencao_inss',
                 'valor_retencao_csll')
    def _compute_total_retencoes(self):
        for item in self:
            total = item.valor_retencao_pis + item.valor_retencao_cofins + \
                item.valor_retencao_irrf + item.valor_retencao_inss + \
                item.valor_retencao_csll
            item.retencoes_federais = total

    model = fields.Selection(
        selection_add=[('014', 'Nota Belo Horizonte')])

    retencoes_federais = fields.Monetary(compute="_compute_total_retencoes")

    @api.multi
    def _hook_validation(self):
        errors = super(InvoiceEletronic, self)._hook_validation()
        if self.model == '014':
            if not self.company_id.l10n_br_inscr_mun:
                errors.append(u'Inscrição municipal obrigatória')
            if not self.company_id.l10n_br_cnae_main_id.code:
                errors.append(u'CNAE Principal da empresa obrigatório')
            for eletr in self.eletronic_item_ids:
                prod = u"Produto: %s - %s" % (eletr.product_id.default_code,
                                              eletr.product_id.name)
                if not eletr.codigo_tributacao_municipio:
                    errors.append(
                        u'Código de Tributação no Munípio obrigatório - %s' %
                        prod)

        return errors

    @api.multi
    def _prepare_eletronic_invoice_values(self):
        res = super(InvoiceEletronic, self)._prepare_eletronic_invoice_values()
        if self.model != '014':
            return res

        tz = pytz.timezone(self.env.user.partner_id.tz) or pytz.utc
        dt_emissao = datetime.strptime(self.data_emissao, DTFT)
        dt_emissao = pytz.utc.localize(dt_emissao).astimezone(tz)
        dt_emissao = dt_emissao.strftime('%Y-%m-%dT%H:%M:%S')

        partner = self.commercial_partner_id
        city_tomador = partner.city_id
        tomador = {
            'tipo_cpfcnpj': 2 if partner.is_company else 1,
            'cnpj_cpf': re.sub('[^0-9]', '',
                               partner.l10n_br_cnpj_cpf or ''),
            'razao_social': partner.l10n_br_legal_name or partner.name,
            'logradouro': partner.street or '',
            'numero': partner.l10n_br_number or '',
            'complemento': partner.street2 or '',
            'bairro': partner.l10n_br_district or 'Sem Bairro',
            'cidade': '%s%s' % (city_tomador.state_id.l10n_br_ibge_code,
                                city_tomador.l10n_br_ibge_code),
            'uf': partner.state_id.code,
            'cep': re.sub('[^0-9]', '', partner.zip),
            'telefone': re.sub('[^0-9]', '', partner.phone or ''),
            'inscricao_municipal': re.sub(
                '[^0-9]', '', partner.l10n_br_inscr_mun or ''),
            'email': self.partner_id.email or partner.email or '',
        }
        city_prestador = self.company_id.partner_id.city_id
        prestador = {
            'cnpj': re.sub(
                '[^0-9]', '',
                self.company_id.partner_id.l10n_br_cnpj_cpf or ''),
            'inscricao_municipal': re.sub(
                '[^0-9]', '',
                self.company_id.partner_id.l10n_br_inscr_mun or ''),
            'cidade': '%s%s' % (city_prestador.state_id.l10n_br_ibge_code,
                                city_prestador.l10n_br_ibge_code),
            'cnae': re.sub('[^0-9]', '',
                           self.company_id.l10n_br_cnae_main_id.code)
        }

        itens_servico = []
        descricao = ''
        codigo_servico = ''
        for item in self.eletronic_item_ids:
            descricao += item.name + '\n'
            itens_servico.append({
                'descricao': item.name,
                'quantidade': str("%.2f" % item.quantidade),
                'valor_unitario': str("%.2f" % item.preco_unitario)
            })
            codigo_servico = item.issqn_codigo

        rps = {
            'numero_lote': self.id,
            'numero': self.numero,
            'serie': self.serie.code or '',
            'tipo_rps': '1',
            'data_emissao': dt_emissao,
            'natureza_operacao': '1',  # Tributada no municipio
            'regime_tributacao': self.company_id.regime_tributacao or '',
            'optante_simples':  # 1 - Sim, 2 - Não
            '2' if self.company_id.l10n_br_fiscal_type == '3' else '1',
            'incentivador_cultural': '2',  # 2 - Não
            'status': '1',  # 1 - Normal
            'valor_servico': str("%.2f" % self.valor_final),
            'valor_deducao': '0',
            'valor_pis': str("%.2f" % self.valor_retencao_pis),
            'valor_cofins': str("%.2f" % self.valor_retencao_cofins),
            'valor_inss': str("%.2f" % self.valor_retencao_inss),
            'valor_ir': str("%.2f" % self.valor_retencao_irrf),
            'valor_csll': str("%.2f" % self.valor_retencao_csll),
            'iss_retido': '1' if self.valor_retencao_issqn > 0 else '2',
            'valor_iss':  str("%.2f" % self.valor_issqn),
            'valor_iss_retido': str("%.2f" % self.valor_retencao_issqn),
            'base_calculo': str("%.2f" % self.valor_final),
            'aliquota_issqn': str("%.4f" % (
                self.eletronic_item_ids[0].issqn_aliquota / 100)),
            'valor_liquido_nfse': str("%.2f" % self.valor_final),
            'codigo_servico': str("%.2f" % float(codigo_servico)),
            'codigo_tributacao_municipio':
            self.eletronic_item_ids[0].codigo_tributacao_municipio,
            # '01.07.00 / 00010700',
            'descricao': descricao,
            'codigo_municipio': prestador['cidade'],
            'itens_servico': itens_servico,
            'tomador': tomador,
            'prestador': prestador,
        }

        res.update(rps)
        return res

    def _find_attachment_ids_email(self):
        atts = super(InvoiceEletronic, self)._find_attachment_ids_email()
        if self.model not in ('014'):
            return atts
        attachment_obj = self.env['ir.attachment']
        attachment_ids = attachment_obj.search(
            [('res_model', '=', 'invoice.eletronic'),
             ('res_id', '=', self.id),
             ('name', 'like', 'nfse-ret')], limit=1, order='id desc')

        for attachment in attachment_ids:
            xml_id = attachment_obj.create(dict(
                name=attachment.name,
                datas_fname=attachment.datas_fname,
                datas=attachment.datas,
                mimetype=attachment.mimetype,
                res_model='account.invoice',
                res_id=self.invoice_id.id,
            ))
            atts.append(xml_id.id)

        danfe_report = self.env['ir.actions.report'].search(
            [('report_name', '=',
              'br_nfse_bh.main_template_br_nfse_bh')])
        report_service = danfe_report.xml_id
        danfse, dummy = self.env.ref(report_service).render_qweb_pdf([self.id])
        report_name = safe_eval(danfe_report.print_report_name,
                                {'object': self, 'time': time})
        filename = "%s.%s" % (report_name, "pdf")
        if danfse:
            danfe_id = attachment_obj.create(dict(
                name=filename,
                datas_fname=filename,
                datas=base64.b64encode(danfse),
                mimetype='application/pdf',
                res_model='account.invoice',
                res_id=self.invoice_id.id,
            ))
            atts.append(danfe_id.id)

        return atts

    @api.multi
    def action_post_validate(self):
        super(InvoiceEletronic, self).action_post_validate()
        if self.model not in ('014'):
            return

        cert = self.company_id.with_context(
            {'bin_size': False}).l10n_br_nfe_a1_file
        cert_pfx = base64.decodestring(cert)

        certificado = Certificado(
            cert_pfx, self.company_id.l10n_br_nfe_a1_password)

        nfse_values = self._prepare_eletronic_invoice_values()
        xml_enviar = xml_gerar_nfse(certificado, rps=nfse_values)

        self.xml_to_send = base64.encodestring(xml_enviar)
        self.xml_to_send_name = 'nfse-enviar-%s.xml' % self.numero

    @api.multi
    def action_send_eletronic_invoice(self):
        super(InvoiceEletronic, self).action_send_eletronic_invoice()
        if self.model != '014' or self.state in ('done', 'cancel'):
            return

        self.state = 'error'
        xml_to_send = base64.decodestring(self.xml_to_send)

        cert = self.company_id.with_context(
            {'bin_size': False}).l10n_br_nfe_a1_file
        cert_pfx = base64.decodestring(cert)

        certificado = Certificado(
            cert_pfx, self.company_id.l10n_br_nfe_a1_password)

        enviar_nfse = gerar_nfse(
            certificado, xml=xml_to_send, ambiente=self.ambiente)
        retorno = enviar_nfse['object']

        if "ListaNfse" in dir(retorno):
            self.state = 'done'
            self.codigo_retorno = '100'
            self.mensagem_retorno = 'NFSe emitida com sucesso'
            self.verify_code = \
                retorno.ListaNfse.CompNfse.Nfse.InfNfse.CodigoVerificacao.text
            self.numero_nfse = retorno.ListaNfse.CompNfse.Nfse.InfNfse.Numero
        else:
            msg = None
            if "ListaMensagemRetorno" in dir(retorno):
                msg = retorno.ListaMensagemRetorno.MensagemRetorno
            else:
                msg = retorno.ListaMensagemRetornoLote.MensagemRetorno
            self.codigo_retorno = msg.Codigo
            self.mensagem_retorno = msg.Mensagem

        self.env['invoice.eletronic.event'].create({
            'code': self.codigo_retorno,
            'name': self.mensagem_retorno,
            'invoice_eletronic_id': self.id,
        })
        self._create_attachment(
            'nfse-envio', self, enviar_nfse['sent_xml'])
        self._create_attachment(
            'nfse-ret', self, enviar_nfse['received_xml'])

    @api.multi
    def action_cancel_document(self, context=None, justificativa=None):
        if self.model not in ('014'):
            return super(InvoiceEletronic, self).action_cancel_document(
                justificativa=justificativa)

        if not justificativa:
            return {
                'name': 'Cancelamento NFe',
                'type': 'ir.actions.act_window',
                'res_model': 'wizard.cancel.nfse',
                'view_type': 'form',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_edoc_id': self.id
                }
            }
        cert = self.company_id.with_context(
            {'bin_size': False}).l10n_br_nfe_a1_file
        cert_pfx = base64.decodestring(cert)
        certificado = Certificado(cert_pfx,
                                  self.company_id.l10n_br_nfe_a1_password)

        company = self.company_id
        city_prestador = self.company_id.partner_id.city_id
        canc = {
            'cnpj_prestador': re.sub('[^0-9]', '', company.l10n_br_cnpj_cpf),
            'inscricao_municipal': re.sub('[^0-9]', '',
                                          company.l10n_br_inscr_mun),
            'cidade': '%s%s' % (city_prestador.state_id.l10n_br_ibge_code,
                                city_prestador.l10n_br_ibge_code),
            'numero_nfse': self.numero_nfse,
            'codigo_cancelamento': '1',  # Erro na emissão
        }
        cancel = cancelar_nfse(
            certificado, cancelamento=canc, ambiente=self.ambiente)

        retorno = cancel['object']
        if "RetCancelamento" in dir(retorno):
            self.state = 'cancel'
            self.codigo_retorno = '100'
            self.mensagem_retorno = u'Nota Fiscal de Serviço Cancelada'
        else:
            # E79 - Nota já está cancelada
            if retorno.ListaMensagemRetorno.MensagemRetorno.Codigo != 'E79':
                mensagem = "%s - %s" % (
                    retorno.ListaMensagemRetorno.MensagemRetorno.Codigo,
                    retorno.ListaMensagemRetorno.MensagemRetorno.Mensagem
                )
                raise UserError(mensagem)

            self.state = 'cancel'
            self.codigo_retorno = '100'
            self.mensagem_retorno = u'Nota Fiscal de Serviço Cancelada'

        self.env['invoice.eletronic.event'].create({
            'code': self.codigo_retorno,
            'name': self.mensagem_retorno,
            'invoice_eletronic_id': self.id,
        })
        self._create_attachment('canc', self, cancel['sent_xml'])
        self._create_attachment('canc-ret', self, cancel['received_xml'])
