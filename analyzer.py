"""
Analyzes contents of the JobBOSS database and produces a report tarball
containing information to help with configuring the integration. The report
will be located at /tmp/jobboss-report-<HOSTNAME>.tar.gz
"""
import common
import csv
import os
import socket
common.configure()
from django.db import connection
from django.db.models import Count
from django.utils.text import slugify
import jobboss.models as jb
from jobboss.export import export_table


def get_database_names():
    """Return a list of database names on this SQL Server instance."""
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT name, database_id, create_date FROM sys.databases;')
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return [
            row['name']
            for row in rows
        ]


def get_sales_codes():
    qs = jb.Job.objects.values('sales_code').annotate(
        count=Count('sales_code')).order_by('-count')
    return {
        row['sales_code']: row['count']
        for row in qs
    }


def export_customers():
    export_table(jb.Customer, '/tmp/report/customers.csv')


def export_ops():
    with open('/tmp/report/wc_op.csv', 'w') as f:
        w = csv.writer(f)
        w.writerow(('Work Center', 'Operation'))
        for operation in jb.Operation.objects.all():
            w.writerow((operation.work_center.work_center, operation.operation))
    with open('/tmp/report/wc.csv', 'w') as f:
        w = csv.writer(f)
        w.writerow(('Work Center',))
        for wc in jb.WorkCenter.objects.all():
            w.writerow((wc.work_center,))
    with open('/tmp/report/vend_svc.csv', 'w') as f:
        w = csv.writer(f)
        w.writerow(('Vendor', 'Service', 'Description'))
        for vs in jb.VendorService.objects.all():
            w.writerow(
                (vs.vendor.vendor, vs.service.service, vs.service.description)
            )


def get_job_so_counts():
    return {
        'jobs': jb.Job.objects.count(),
        'so_items': jb.SoDetail.objects.count()
    }


if __name__ == '__main__':
    os.system('mkdir /tmp/report')
    with open('/tmp/report/report.txt', 'w') as f:
        f.write('JobBOSS Analysis Report\n\n')
        f.write('Available databases:\n')
        for name in get_database_names():
            f.write(name + '\n')
        f.write('\n\nSales codes:\n')
        for sales_code, count in get_sales_codes().items():
            if sales_code is not None:
                f.write('{} ({} jobs)\n'.format(sales_code, count))
        f.write('\n\nSales orders:\n')
        counts = get_job_so_counts()
        f.write('Jobs: {}\n'.format(counts['jobs']))
        f.write('Sales Order Items: {}\n\n'.format(counts['so_items']))
    export_customers()
    export_ops()
    os.system('cd /tmp/report; tar czf ../jobboss-report-{}.tar.gz *'.format(
        slugify(socket.gethostname())
    ))
