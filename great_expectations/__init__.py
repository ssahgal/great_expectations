from ._version import get_versions
__version__ = get_versions()['version']
del get_versions

from .util import from_pandas, read_csv, read_excel, read_json, read_parquet, read_table, validate

from great_expectations import data_asset
from great_expectations import data_context
