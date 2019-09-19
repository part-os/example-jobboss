import sys
from common import PAPERLESS_CONFIG, logger
from paperless.client import PaperlessClient
from paperless.listeners import OrderListener
from paperless.main import PaperlessSDK
from paperless.objects.orders import Order
from job import process_order


class MyOrderListener(OrderListener):
    def on_event(self, resource):
        if resource.status != 'cancelled':
            process_order(resource)


def main():
    PaperlessClient(
        access_token=PAPERLESS_CONFIG.token,
        group_slug=PAPERLESS_CONFIG.slug
    )
    my_sdk = PaperlessSDK(loop=False)
    listener = MyOrderListener()
    my_sdk.add_listener(listener)
    my_sdk.run()


if __name__ == '__main__':
    try:
        order_num = int(sys.argv[1])
    except (IndexError, ValueError):
        order_num = None
    if order_num is not None:
        PaperlessClient(
            access_token=PAPERLESS_CONFIG.token,
            group_slug=PAPERLESS_CONFIG.slug
        )
        order = Order.get(order_num)
        process_order(order)
    else:
        if PAPERLESS_CONFIG.active:
            logger.info('Running connector!')
            main()
        else:
            logger.debug('Inactive')
