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
from routing import generate_routing_lines, OP_MAP, FINISH_MAP, is_inside_op, \
    is_outside_op, RoutingLine


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
            sum([len([comp for comp in oi.components if not comp.is_hardware])
                 for oi in order.order_items]),
            jb.Job.objects.count()
        )
        op_count = 0
        for oi in order.order_items:
            for comp in oi.components:
                op_count += len(comp.shop_operations)
        addon_count = sum(len(oi.ordered_add_ons) for oi in order.order_items)
        self.assertEqual(op_count + addon_count, jb.JobOperation.objects.count())

    def test_routing(self):
        inside_name = 'Test Paperless Op'
        outside_name = 'Anodizing'
        OP_MAP[inside_name] = [['WC1', 'OP1']]
        FINISH_MAP[outside_name] = [['VENDOR1', 'SERVICE1']]
        lines = list(generate_routing_lines('No op'))
        self.assertEqual(1, len(lines))
        line: RoutingLine = lines[0]
        self.assertTrue(line.is_inside)
        self.assertEqual('No op', line.wc)
        self.assertFalse(is_inside_op('No op'))
        self.assertFalse(is_outside_op('No op'))
        lines = list(generate_routing_lines(inside_name))
        self.assertEqual(1, len(lines))
        line: RoutingLine = lines[0]
        self.assertTrue(line.is_inside)
        self.assertEqual('WC1', line.wc)
        self.assertTrue(is_inside_op(inside_name))
        self.assertFalse(is_outside_op(inside_name))
        lines = list(generate_routing_lines(outside_name))
        self.assertEqual(1, len(lines))
        line: RoutingLine = lines[0]
        self.assertFalse(line.is_inside)
        self.assertEqual('VENDOR1', line.vendor)
        self.assertFalse(is_inside_op(outside_name))
        self.assertTrue(is_outside_op(outside_name))
        OP_MAP[inside_name] = []
        lines = list(generate_routing_lines(inside_name))
        self.assertEqual(0, len(lines))
        OP_MAP.pop(inside_name)
        FINISH_MAP.pop(outside_name)


if __name__ == '__main__':
    from django.test.utils import setup_databases
    setup_databases(1, False)
    unittest.main()
