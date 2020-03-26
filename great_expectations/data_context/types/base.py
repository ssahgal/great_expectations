import uuid
from copy import deepcopy
import logging

from marshmallow import Schema, fields, ValidationError, INCLUDE, post_load, validates_schema, post_dump
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

import great_expectations.exceptions as ge_exceptions
from great_expectations.types import DictDot
from great_expectations.types.configurations import ClassConfigSchema

logger = logging.getLogger(__name__)

yaml = YAML()

CURRENT_CONFIG_VERSION = 1
MINIMUM_SUPPORTED_CONFIG_VERSION = 1
DEFAULT_USAGE_STATISTICS_URL = "https://stats.greatexpectations.io/great_expectations/v1/usage_statistics"


class DataContextConfig(DictDot):
    def __init__(
            self,
            config_version,
            datasources,
            expectations_store_name,
            validations_store_name,
            evaluation_parameter_store_name,
            plugins_directory,
            validation_operators,
            stores,
            data_docs_sites,
            config_variables_file_path=None,
            anonymous_usage_statistics=None,
            commented_map=None
    ):
        if commented_map is None:
            commented_map = CommentedMap()
        self._commented_map = commented_map
        self._config_version = config_version
        if datasources is None:
            datasources = {}
        self.datasources = datasources
        self.expectations_store_name = expectations_store_name
        self.validations_store_name = validations_store_name
        self.evaluation_parameter_store_name = evaluation_parameter_store_name
        self.plugins_directory = plugins_directory
        if not isinstance(validation_operators, dict):
            raise ValueError("validation_operators must be configured with a dictionary")
        self.validation_operators = validation_operators
        self.stores = stores
        self.data_docs_sites = data_docs_sites
        self.config_variables_file_path = config_variables_file_path
        if anonymous_usage_statistics is None:
            anonymous_usage_statistics = AnonymizedUsageStatisticsConfig()
        elif isinstance(anonymous_usage_statistics, dict):
            anonymous_usage_statistics = AnonymizedUsageStatisticsConfig(**anonymous_usage_statistics)
        self.anonymous_usage_statistics = anonymous_usage_statistics

    @property
    def commented_map(self):
        return self._commented_map

    @property
    def config_version(self):
        return self._config_version

    @classmethod
    def from_commented_map(cls, commented_map):
        try:
            config = dataContextConfigSchema.load(commented_map)
            return cls(commented_map=commented_map, **config)
        except ValidationError:
            logger.error("Encountered errors during loading data context config. See ValidationError for more details.")
            raise

    def to_yaml(self, outfile):
        commented_map = deepcopy(self.commented_map)
        commented_map.update(dataContextConfigSchema.dump(self))
        yaml.dump(commented_map, outfile)


class DatasourceConfig(DictDot):
    def __init__(self, class_name, module_name=None, data_asset_type=None, generators=None, credentials=None,
                 reader_method=None, limit=None, **kwargs):
        # NOTE - JPC - 20200316: Currently, we are mostly inconsistent with respect to this type...
        self._class_name = class_name
        self._module_name = module_name
        self.data_asset_type = data_asset_type
        if generators is not None:
            self.generators = generators
        if credentials is not None:
            self.credentials = credentials
        if reader_method is not None:
            self.reader_method = reader_method
        if limit is not None:
            self.limit = limit
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def class_name(self):
        return self._class_name

    @property
    def module_name(self):
        return self._module_name


class AnonymizedUsageStatisticsConfig(DictDot):
    def __init__(self, enabled=True, data_context_id=None, usage_statistics_url=None):
        self._enabled = enabled
        if data_context_id is None:
            data_context_id = str(uuid.uuid4())
            self._explicit_id = False
        else:
            self._explicit_id = True

        self._data_context_id = data_context_id
        if usage_statistics_url is None:
            usage_statistics_url = DEFAULT_USAGE_STATISTICS_URL
            self._explicit_url = False
        else:
            self._explicit_url = True
        self._usage_statistics_url = usage_statistics_url

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError("usage statistics enabled property must be boolean")
        self._enabled = enabled

    @property
    def data_context_id(self):
        return self._data_context_id

    @data_context_id.setter
    def data_context_id(self, data_context_id):
        try:
            uuid.UUID(data_context_id)
        except ValueError:
            raise ge_exceptions.InvalidConfigError("data_context_id must be a valid uuid")
        self._data_context_id = data_context_id
        self._explicit_id = True

    @property
    def explicit_id(self):
        return self._explicit_id

    @property
    def usage_statistics_url(self):
        return self._usage_statistics_url

    @usage_statistics_url.setter
    def usage_statistics_url(self, usage_statistics_url):
        self._usage_statistics_url = usage_statistics_url
        self._explicit_url = True


class AnonymizedUsageStatisticsConfigSchema(Schema):
    data_context_id = fields.UUID(required=False)
    enabled = fields.Boolean(default=True)
    usage_statistics_url = fields.URL(allow_none=True)
    _explicit_url = fields.Boolean(required=False)

    # noinspection PyUnusedLocal
    @post_load()
    def make_usage_statistics_config(self, data, **kwargs):
        if "data_context_id" in data:
            data["data_context_id"] = str(data["data_context_id"])
        return AnonymizedUsageStatisticsConfig(**data)

    # noinspection PyUnusedLocal
    @post_dump()
    def filter_implicit(self, data, **kwargs):
        if not data.get("_explicit_url") and "usage_statistics_url" in data:
            del data["usage_statistics_url"]
        if "_explicit_url" in data:
            del data["_explicit_url"]
        return data


class DatasourceConfigSchema(Schema):
    class Meta:
        unknown = INCLUDE

    class_name = fields.String(required=True)
    module_name = fields.String(missing="great_expectations.datasource")
    data_asset_type = fields.Nested(ClassConfigSchema)
    # TODO: Update to generator-specific
    # generators = fields.Mapping(keys=fields.Str(), values=fields.Nested(fields.GeneratorSchema))
    generators = fields.Dict(keys=fields.Str(), values=fields.Dict(), allow_none=True)
    credentials = fields.Raw(allow_none=True)

    # noinspection PyUnusedLocal
    @post_load
    def make_datasource_config(self, data, **kwargs):
        # Why this validation isn't working natively, I don't know
        if "class_name" not in data:
            raise ValidationError("missing field: class_name")
        return DatasourceConfig(**data)


class DataContextConfigSchema(Schema):
    config_version = fields.Number(validate=lambda x: 0 < x < 100, error_messages={"invalid": "config version must "
                                                                                              "be a number."})
    datasources = fields.Dict(keys=fields.Str(), values=fields.Nested(DatasourceConfigSchema))
    expectations_store_name = fields.Str()
    validations_store_name = fields.Str()
    evaluation_parameter_store_name = fields.Str()
    plugins_directory = fields.Str(allow_none=True)
    validation_operators = fields.Dict(keys=fields.Str(), values=fields.Dict())
    stores = fields.Dict(keys=fields.Str(), values=fields.Dict())
    data_docs_sites = fields.Dict(keys=fields.Str(), values=fields.Dict(), allow_none=True)
    config_variables_file_path = fields.Str(allow_none=True)
    anonymous_usage_statistics = fields.Nested(AnonymizedUsageStatisticsConfigSchema)

    # noinspection PyMethodMayBeStatic
    # noinspection PyUnusedLocal
    def handle_error(self, exc, data, **kwargs):
        """Log and raise our custom exception when (de)serialization fails."""
        logger.error(exc.messages)
        raise ge_exceptions.InvalidDataContextConfigError("Error while processing DataContextConfig.",
                                                          exc)

    @validates_schema
    def validate_schema(self, data, **kwargs):
        if 'config_version' not in data:
            raise ge_exceptions.InvalidDataContextConfigError(
                "The key `config_version` is missing; please check your config file.",
                validation_error=ValidationError("no config_version key"))

        if not isinstance(data['config_version'], (int, float)):
            raise ge_exceptions.InvalidDataContextConfigError(
                "The key `config_version` must be a number. Please check your config file.",
                validation_error=ValidationError("config version not a number")
            )

        # When migrating from 0.7.x to 0.8.0
        if data['config_version'] == 0 and (
                "validations_store" in list(data.keys()) or "validations_stores" in list(data.keys())):
            raise ge_exceptions.UnsupportedConfigVersionError(
                "You appear to be using a config version from the 0.7.x series. This version is no longer supported."
            )
        elif data['config_version'] < MINIMUM_SUPPORTED_CONFIG_VERSION:
            raise ge_exceptions.UnsupportedConfigVersionError(
                "You appear to have an invalid config version ({}).\n    The version number must be between {} and {}.".format(
                    data['config_version'],
                    MINIMUM_SUPPORTED_CONFIG_VERSION,
                    CURRENT_CONFIG_VERSION,
                ),
            )
        elif data['config_version'] > CURRENT_CONFIG_VERSION:
            raise ge_exceptions.InvalidDataContextConfigError(
                "You appear to have an invalid config version ({}).\n    The maximum valid version is {}.".format(
                    data['config_version'],
                    CURRENT_CONFIG_VERSION
                ),
                validation_error=ValidationError("config version too high")
            )


dataContextConfigSchema = DataContextConfigSchema()
datasourceConfigSchema = DatasourceConfigSchema()
anonymizedUsageStatisticsSchema = AnonymizedUsageStatisticsConfigSchema()
