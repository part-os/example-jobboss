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
        self.assertEqual(11, jb.Job.objects.count())


if __name__ == '__main__':
    from django.test.utils import setup_databases
    setup_databases(1, False)
    unittest.main()
