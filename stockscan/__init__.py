from .scanner import Scanner, ScanResult, Item, ALL_SCANNERS
from .dummy import DummyScanner
from .monitor import StockMonitor

import importlib
import pkgutil

from . import vendors

for loader, name, is_pkg in pkgutil.walk_packages(vendors.__path__):
    importlib.import_module(vendors.__name__ + '.' + name)

__all__ = ['Scanner',
           'DummyScanner',
           'StockMonitor',
           'ScanResult',
           'Item',
           'ALL_SCANNERS']
