from jobboss.query.job import get_work_center, get_operation, get_vendor, \
    get_default_vendor, get_default_work_center

OP_MAP = {}
"""Example: "Saw": [["SAW", "SC"]]"""

FINISH_MAP = {}
"""Example: "Anodize MIL-A-8624": [["PLATECO", "An A-8624"]]"""


class RoutingLine:
    _INITIAL = object()

    def __init__(self, wc=None, operation=None, vendor=None, service=None,
                 description=None, is_inside=False):
        self.wc = wc
        self.operation = operation
        self.vendor = vendor
        self.service = service
        self.description = description
        self.is_inside = is_inside
        self._work_center = self._INITIAL  # cache work center lookup
        self._has_work_center = None
        self._vendor = self._INITIAL
        self._has_vendor = None
        self._has_operation = None
        self._operation = self._INITIAL

    @property
    def has_work_center(self):
        """Returns True if this routing line maps to a real work center.
        False indicates this maps to the default work center."""
        if self._has_work_center is None:
            _ = self.work_center_instance
        return self._has_work_center

    @property
    def work_center_instance(self):
        if self._work_center is self._INITIAL:
            self._work_center = get_work_center(self.wc)
            self._has_work_center = self._work_center is not None
        if self._has_work_center:
            return self._work_center
        else:
            return get_default_work_center()

    @property
    def has_operation(self):
        """Returns True if this routing maps to a real operation."""
        if self._has_operation is None:
            _ = self.operation_instance
        return self._has_operation

    @property
    def operation_instance(self):
        if self._operation is self._INITIAL:
            self._operation = get_operation(self.operation)
            self._has_operation = self._operation is not None
        return self._operation

    @property
    def notes(self):
        if self.is_inside and not self.has_work_center:
            return BAD_MAP_NOTE_TEXT
        else:
            return None

    @property
    def has_vendor(self):
        if self._has_vendor is None:
            _ = self.vendor_instance
        return self._has_vendor

    @property
    def vendor_instance(self):
        if self._vendor is self._INITIAL:
            self._vendor = get_vendor(self.vendor)
            self._has_vendor = self._vendor is not None
        if self._has_vendor:
            return self._vendor
        else:
            return get_default_vendor()


def is_outside_op(name):
    return name in FINISH_MAP.keys()


def is_inside_op(name):
    return name in OP_MAP.keys()


BAD_MAP_NOTE_TEXT = 'Paperless Parts could not match this operation to a ' \
                    'work center or outside service. If this is a new ' \
                    'operation, please add the work center or service to ' \
                    'JobBOSS. To update the mapping between Paperless ' \
                    'operation names and JobBOSS work center / operation ' \
                    'names, contact support@paperlessparts.com.'


def generate_routing_lines(pp_name):
    """Yield operations as (wc/vendor, service, is_outside, note)"""
    if is_outside_op(pp_name):
        for vendor, service in FINISH_MAP[pp_name]:
            yield RoutingLine(vendor=vendor, service=service, is_inside=False,
                              description=pp_name)
    elif is_inside_op(pp_name):
        for wc_name, op_name in OP_MAP[pp_name]:
            yield RoutingLine(wc=wc_name, operation=op_name, is_inside=True,
                              description=pp_name)
    else:
        yield RoutingLine(wc=pp_name, is_inside=True, description=pp_name)
