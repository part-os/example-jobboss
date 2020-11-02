import argparse
import sys
import common
from common import logger
from paperless.client import PaperlessClient
from paperless.listeners import OrderListener
from paperless.main import PaperlessSDK
from paperless.objects.orders import Order
common.configure()
from job import process_order


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
    parser = argparse.ArgumentParser()
    parser.add_argument('--order_num')
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--create_db_snapshot', action='store_true')
    parser.add_argument('--compare_db_snapshots', action='store_true')
    parser.add_argument('--snapshot_file_path', default=None, type=str,
                        help='The file path for the snapshot pickle file. If you are creating a new snapshot, you '
                             'may specify the path with this argument. If you are comparing two existing snapshots, '
                             'this is the path of the "new" snapshot and this must be supplied.')
    parser.add_argument('--old_snapshot_file_path', default=None, type=str,
                        help='When comparing two snapshots, this is the file path of the "old" snapshot.')
    args = parser.parse_args()

    if args.order_num is not None:
        PaperlessClient(
            access_token=common.PAPERLESS_CONFIG.token,
            group_slug=common.PAPERLESS_CONFIG.slug
        )
        order = Order.get(args.order_num)
        process_order(order)
    elif args.test:
        print('Testing JobBOSS Connection')
        print('Host:', common.JOBBOSS_CONFIG.host)
        print('Database:', common.JOBBOSS_CONFIG.name)
        print('Username:', common.JOBBOSS_CONFIG.user)
        from jobboss.models import Job
        c = Job.objects.count()
        print('Job count: {} OK!'.format(c))
    elif args.create_db_snapshot:
        if args.snapshot_file_path is None:
            now = datetime.now().strftime('%Y.%m.%d.%H.%M.%S')
            database_snapshot_file_path = f'database_snapshot_{now}.pickle'
        else:
            database_snapshot_file_path = args.snapshot_file_path
        print(f'Creating a snapshot of the database: {database_snapshot_file_path}')
        from jobboss.utils.database_diff import create_database_snapshot
        create_database_snapshot(database_snapshot_file_path)
    elif args.compare_db_snapshots:
        if args.snapshot_file_path is None or args.old_snapshot_file_path is None:
            raise ValueError('Must supply both --snapshot_file_path and --old_snapshot_file_path when comparing snapshots.')
        from joboss.utils.database_diff import compare_database_snapshots
        compare_database_snapshots(args.old_snapshot_file_path, args.snapshot_file_path)
    else:
        if common.PAPERLESS_CONFIG.active:
            logger.info('Running connector!')
            main()
        else:
            logger.debug('Inactive')
