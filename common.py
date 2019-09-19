import configparser
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import sys

CONFIG_PATH = 'paperless.ini'
PAPERLESS_CONFIG = None
JOBBOSS_CONFIG = None

logger = logging.getLogger('paperless')
logger.setLevel(logging.DEBUG)
f = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ph = logging.StreamHandler(sys.stdout)
ph.setFormatter(f)
logger.addHandler(ph)


class PaperlessConfig:
    def __init__(self, **kwargs):
        self.token = kwargs.get('token')
        self.slug = kwargs.get('slug')
        self.logpath = kwargs.get('logpath')
        self.active = kwargs.get('active')


class JobBOSSConfig:
    def __init__(self, **kwargs):
        self.host = kwargs.get('host')
        self.name = kwargs.get('name')
        self.user = kwargs.get('user')
        self.password = kwargs.get('password')
        self.paperless_user = kwargs.get('paperless_user')
        self.sales_code = kwargs.get('sales_code')
        self.import_material = bool(kwargs.get('import_material'))
        self.default_location = kwargs.get('default_location')
        self.import_operations = bool(kwargs.get('import_operations'))


logger.info('Reading configuration file')
parser = configparser.ConfigParser()
parser.read('paperless.ini')

PAPERLESS_CONFIG = PaperlessConfig(
    token=parser['Paperless']['token'],
    slug=parser['Paperless']['slug'],
    logpath=parser['Paperless']['logpath'],
    active=bool(int(parser['Paperless']['active']))
)
fh = TimedRotatingFileHandler(
    PAPERLESS_CONFIG.logpath,
    backupCount=30,
    when='midnight',
    interval=1
)
fh.suffix = '%Y-%m-%d'
fh.setFormatter(f)
fh.setLevel(logging.INFO)
logger.addHandler(fh)

JOBBOSS_CONFIG = JobBOSSConfig(
    host=parser['JobBOSS']['host'],
    name=parser['JobBOSS']['name'],
    user=parser['JobBOSS']['user'],
    password=parser['JobBOSS']['password'],
    paperless_user=parser['JobBOSS']['paperless_user'],
    sales_code=parser['JobBOSS']['sales_code'],
    import_material=parser['JobBOSS']['import_material'],
    default_location=parser['JobBOSS']['default_location'],
    import_operations=parser['JobBOSS']['import_operations'],
)
os.environ.setdefault('JOBBOSS_DB_HOST', JOBBOSS_CONFIG.host)
os.environ.setdefault('JOBBOSS_DB_NAME', JOBBOSS_CONFIG.name)
os.environ.setdefault('JOBBOSS_DB_USERNAME', JOBBOSS_CONFIG.user)
os.environ.setdefault('JOBBOSS_DB_PASSWORD', JOBBOSS_CONFIG.password)
