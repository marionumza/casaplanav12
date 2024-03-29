# -*- coding: utf-8 -*-
# © 2014  Renato Lima - Akretion
# © 2013  Raphaël Valyi - Akretion
# © 2016 Danimar Ribeiro, Trustcode
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from datetime import timedelta

from odoo import api, fields, models, _
from odoo.addons import decimal_precision as dp
from odoo.exceptions import UserError
from odoo.osv import expression
import logging
_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    @api.depends('order_line.price_total')
    def _amount_all(self):
        super(SaleOrder, self)._amount_all()
        for order in self:
            order.update({
                'amount_total': order.total_bruto - order.total_desconto +
                order.total_tax + order.total_frete + order.total_seguro +
                order.total_despesas,
            })

    def _calc_ratio(self, qty, total):
        if total > 0:
            return qty / total
        else:
            return 0

    @api.onchange('total_despesas', 'total_seguro', 'total_frete')
    def _onchange_despesas_frete_seguro(self):
        amount = 0
        for line in self.order_line:
            if line.product_id.fiscal_type == 'product':
                amount += line.valor_bruto - line.valor_desconto

        index = 0
        prec = self.currency_id.decimal_places
        balance_seguro = self.total_seguro
        balance_frete = self.total_frete
        balance_despesas = self.total_despesas
        total_items = len(self.order_line)

        for l in self.order_line:
            index += 1
            if l.product_id.fiscal_type == 'service':
                continue
            item_liquido = l.valor_bruto - l.valor_desconto
            percentual = self._calc_ratio(item_liquido, amount)
            if index == total_items:
                amount_seguro = balance_seguro
                amount_frete = balance_frete
                amount_despesas = balance_despesas
            else:
                amount_seguro = round(self.total_seguro * percentual, prec)
                amount_frete = round(self.total_frete * percentual, prec)
                amount_despesas = round(self.total_despesas * percentual, prec)
            l.update({
                'valor_seguro': amount_seguro,
                'valor_frete': amount_frete,
                'outras_despesas': amount_despesas
            })
            balance_seguro -= amount_seguro
            balance_frete -= amount_frete
            balance_despesas -= amount_despesas

    total_despesas = fields.Float(
        string='Despesas ( + )', default=0.00,
        digits=dp.get_precision('Account'),
        readonly=True, states={'draft': [('readonly', False)],
                               'sent': [('readonly', False)]})
    total_seguro = fields.Float(
        string='Seguro ( + )', default=0.00,
        digits=dp.get_precision('Account'),
        readonly=True, states={'draft': [('readonly', False)],
                               'sent': [('readonly', False)]})
    total_frete = fields.Float(
        string='Frete ( + )', default=0.00, digits=dp.get_precision('Account'),
        readonly=True, states={'draft': [('readonly', False)],
                               'sent': [('readonly', False)]})

    @api.multi
    def action_confirm(self):
        for order in self:
            prec = order.currency_id.decimal_places
            itens = order.order_line
            frete = round(sum(x.valor_frete for x in itens), prec)
            if frete != order.total_frete:
                raise UserError("A soma do frete dos itens não confere com o\
                                valor total do frete. Insira novamente o valor\
                                total do frete para que o mesmo seja rateado\
                                entre os itens.")

            despesas = round(sum(x.outras_despesas for x in itens), prec)
            if despesas != order.total_despesas:
                raise UserError("A soma de outras despesas dos itens não\
                                confere com o valor total de outras despesas.\
                                Insira novamente o valor total de outras\
                                despesas para que o mesmo seja rateado entre\
                                os itens.")

            seguro = round(sum(x.valor_seguro for x in itens), prec)
            if seguro != order.total_seguro:
                raise UserError("A soma do seguro dos itens não confere com o\
                                valor total do seguro. Insira novamente o\
                                valor total do seguro para que o mesmo seja\
                                rateado entre os itens.")

        return super(SaleOrder, self).action_confirm()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _prepare_tax_context(self):
        res = super(SaleOrderLine, self)._prepare_tax_context()
        res.update({
            'valor_frete': self.valor_frete,
            'valor_seguro': self.valor_seguro,
            'outras_despesas': self.outras_despesas,
        })
        return res

    @api.multi
    def _prepare_order_line_procurement(self, group_id=False):
        vals = super(SaleOrderLine, self)._prepare_order_line_procurement(
            group_id=group_id)
        confirm = fields.Date.from_string(self.order_id.confirmation_date)
        date_planned = confirm + timedelta(days=self.customer_lead or 0.0)
        date_planned -= timedelta(days=self.order_id.company_id.security_lead)
        vals["date_planned"] = date_planned
        return vals

    valor_seguro = fields.Float(
        'Seguro', default=0.0, digits=dp.get_precision('Account'))
    outras_despesas = fields.Float(
        'Despesas', default=0.0, digits=dp.get_precision('Account'))
    valor_frete = fields.Float(
        'Frete', default=0.0, digits=dp.get_precision('Account'))

    @api.multi
    def _prepare_invoice_line(self, qty):
        res = super(SaleOrderLine, self)._prepare_invoice_line(qty)

        res['valor_seguro'] = self.valor_seguro
        res['outras_despesas'] = self.outras_despesas
        res['valor_frete'] = self.valor_frete * (round(
            res['quantity'] / self.product_uom_qty, 2))
        return res

class ProcurementGroup(models.Model):

    _inherit = 'procurement.group'
    _description = 'Procurement Requisition'
    _order = "id desc"

    @api.model
    def run(self, product_id, product_qty, product_uom, location_id, name, origin, values):
        values.setdefault('company_id', self.env['res.company']._company_default_get('procurement.group'))
        values.setdefault('priority', '1')
        values.setdefault('date_planned', fields.Datetime.now())
        rule = self._get_rule(product_id, location_id, values)
        if not rule:
            raise UserError(_('No procurement rule found. Please verify the configuration of %s routes, product id %s') % (product_id.name, product_id.id, ))
        getattr(rule, '_run_%s' % rule.action)(product_id, product_qty, product_uom, location_id, name, origin, values)
        return True

    @api.model
    def _search_rule(self, product_id, values, domain):
        """ First find a rule among the ones defined on the procurement
        group; then try on the routes defined for the product; finally fallback
        on the default behavior """
        if values.get('warehouse_id', False):
            domain = expression.AND([['|', ('warehouse_id', '=', values['warehouse_id'].id), ('warehouse_id', '=', False)], domain])
        Pull = self.env['procurement.rule']
        res = self.env['procurement.rule']
        _logger.info("=======product_id=====%s========%s",product_id, domain)
        if values.get('route_ids', False):
            res = Pull.search(expression.AND([[('route_id', 'in', values['route_ids'].ids)], domain]), order='route_sequence, sequence', limit=1)
            _logger.info("=======values==%s=====%s",res, values.get('route_ids', False))
        if not res:
            product_routes = product_id.route_ids | product_id.categ_id.total_route_ids
            if product_routes:
                res = Pull.search(expression.AND([[('route_id', 'in', product_routes.ids)], domain]), order='route_sequence, sequence', limit=1)
            _logger.info("=======product_routes not res=1===%s=======%s",res, product_routes)
        if not res:
            warehouse_routes = values['warehouse_id'].route_ids
            if warehouse_routes:
                res = Pull.search(expression.AND([[('route_id', 'in', warehouse_routes.ids)], domain]), order='route_sequence, sequence', limit=1)
            _logger.info("=======warehouse_routes not res=2====%s======%s======%s",res, warehouse_routes, [[('route_id', 'in', warehouse_routes.ids)], domain])
        return res