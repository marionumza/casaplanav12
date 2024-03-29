# -*- coding: utf-8 -*-
# © 2016 Danimar Ribeiro, Trustcode
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

{  # pylint: disable=C8101,C8103
    'name': 'Brazilian Localization Account',
    'description': """Brazilian Localization Account""",
    'version': '11.0.1.0.0',
    'category': 'account',
    'author': 'Trustcode',
    'license': 'AGPL-3',
    'website': 'http://www.trustcode.com.br',
    'contributors': [
        'Danimar Ribeiro <danimaribeiro@gmail.com>'
    ],
    'depends': [
        'account', 'br_base', 'account_cancel', 'br_localization_filtering',
    ],
    'data': [
        'views/account_fiscal_position_view.xml',
        'views/account_invoice_view.xml',
        'views/account.xml',
        'views/br_account_view.xml',
        'views/product_view.xml',
        'views/res_company_view.xml',
        'views/account_tax.xml',
        'views/product_fiscal_classification.xml',
        'views/account_invoice_refund.xml',
        'views/res_config_settings.xml',
        'wizard/br_product_fiscal_classification_wizard.xml',
        'security/ir.model.access.csv',
        'reports/account_invoice.xml',
    ],
}
