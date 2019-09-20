import sys
import common
from common import logger
from paperless.client import PaperlessClient
from paperless.listeners import OrderListener
from paperless.main import PaperlessSDK
from paperless.objects.orders import Order
from job import process_order

common.configure()


class MyOrderListener(OrderListener):
    def on_event(self, resource):
        if resource.status != 'cancelled':
            process_order(resource)


def main():
    PaperlessClient(
        access_token=common.PAPERLESS_CONFIG.token,
        group_slug=common.PAPERLESS_CONFIG.slug
    )
    my_sdk = PaperlessSDK(loop=False)
    listener = MyOrderListener()
    my_sdk.add_listener(listener)
    my_sdk.run()


if __name__ == '__main__':
    test_mode = False
    try:
        if sys.argv[1] == 'test':
            test_mode = True
            order_num = None
        else:
            order_num = int(sys.argv[1])
    except (IndexError, ValueError):
        order_num = None
    if order_num is not None:
        PaperlessClient(
            access_token=common.PAPERLESS_CONFIG.token,
            group_slug=common.PAPERLESS_CONFIG.slug
        )
        order = Order.get(order_num)
        process_order(order)
    elif test_mode:
        print('Testing JobBOSS Connection')
        print('Host:', common.JOBBOSS_CONFIG.host)
        print('Database:', common.JOBBOSS_CONFIG.name)
        print('Username:', common.JOBBOSS_CONFIG.user)
        from jobboss.models import Job
        c = Job.objects.count()
        print('Job count: {} OK!'.format(c))
    else:
        if common.PAPERLESS_CONFIG.active:
            logger.info('Running connector!')
            main()
        else:
            logger.debug('Inactive')
