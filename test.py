"""
To run tests:

1. activate virtual environment; for example:
    source osenv/bin/activate

2. run this module as a script:
    python test.py
"""
import sys
import os
sys.path.append('jobboss-python')
sys.path.append('core-python')
os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',
    'jobboss.settings'
)
import unittest
from unittest.mock import MagicMock
import common
import json
from django.db.models import F
from paperless.client import PaperlessClient
from paperless.objects.orders import Order

common.configure(test_mode=True)


class ConnectorTest(unittest.TestCase):
    def test_connector(self):
        import jobboss.models as jb
        jb.AutoNumber.objects.create(
            type='SalesOrder',
            system_generated=True,
            last_nbr=1
        )
        jb.AutoNumber.objects.create(
            type='Job',
            system_generated=True,
            last_nbr=1
        )
        from job import process_order
        with open('core-python/tests/unit/mock_data/order.json') as data_file:
            mock_order_json = json.load(data_file)
        client = PaperlessClient()
        client.get_resource = MagicMock(return_value=mock_order_json)
        order = Order.get(1)
        process_order(order)
        self.assertEqual(
            len(order.order_items),
            jb.Job.objects.filter(job=F('top_lvl_job')).count()
        )
        self.assertEqual(
            sum([len(oi.components) for oi in order.order_items]),
            jb.Job.objects.count()
        )
        op_count = 0
        for oi in order.order_items:
            for comp in oi.components:
                op_count += len(comp.shop_operations)
        addon_count = sum(len(oi.ordered_add_ons) for oi in order.order_items)
        self.assertEqual(op_count + addon_count, jb.JobOperation.objects.count())


if __name__ == '__main__':
    from django.test.utils import setup_databases
    setup_databases(1, False)
    unittest.main()
