# -*- coding: utf-8 -*-
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{  # pylint: disable=C8101,C8103
    'name': 'Brazilian Localization Sale Payment',
    'description': 'Brazilian Localization for Sale Payment',
    'category': 'Localisation',
    'license': 'AGPL-3',
    'author': 'Udoo',
    'website': 'http://www.udoo.com.br',
    'version': '11.0.1.0.0',
    'depends': [
        'sale', 'br_account_payment',
    ],
    'data': [
        'views/sale_order.xml',
    ],
    'auto_install': True
}
