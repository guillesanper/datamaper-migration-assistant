"""Unit tests for connector name resolution and exact quoting of catalog names."""

import hashlib
from unittest.mock import Mock

import pytest

from app.models.db_metadata import ColumnMetadata, DataType, TableMetadata
from app.services.connector_resolver import (
    ConnectorNameResolver,
    HashNotFoundError,
    MigrationScriptServiceError,
    SqlName,
)
from app.services.migration_script_service import MigrationScriptService
from app.utils.db_adapters.exceptions import DBQueryExecutionError
from app.utils.sql_safety import UnsafeSQLError, quote_exact_identifier


def sha(name):
    return hashlib.sha256(name.encode()).hexdigest()


def make_adapter(tables_by_schema, default="public", columns=None):
    adapter = Mock()
    adapter._get_default_schema.return_value = default
    adapter.get_schemas.return_value = list(tables_by_schema)

    def get_tables(schema):
        value = tables_by_schema[schema]
        if isinstance(value, Exception):
            raise value
        return [TableMetadata(name=name, schema=schema) for name in value]

    adapter.get_tables.side_effect = get_tables
    adapter.get_columns.side_effect = lambda table, schema: [
        ColumnMetadata(name=c, data_type=DataType.TEXT, native_type="TEXT", ordinal_position=i)
        for i, c in enumerate((columns or {}).get((schema, table), []), start=1)
    ]
    return adapter


class TestQuoteExactIdentifier:
    @pytest.mark.parametrize(
        "dialect,expected",
        [
            ("postgresql", '"MixedCase"'),
            ("oracle", '"MixedCase"'),
            ("mysql", "`MixedCase`"),
            ("sqlserver", "[MixedCase]"),
        ],
    )
    def test_always_quotes(self, dialect, expected):
        assert quote_exact_identifier("MixedCase", dialect) == expected

    def test_dots_are_part_of_the_name(self):
        assert quote_exact_identifier("a.b", "postgresql") == '"a.b"'

    def test_escapes_closing_quote(self):
        assert quote_exact_identifier('x"; DROP', "postgresql") == '"x""; DROP"'
        assert quote_exact_identifier("x]; DROP", "sqlserver") == "[x]]; DROP]"

    def test_rejects_control_characters(self):
        with pytest.raises(UnsafeSQLError):
            quote_exact_identifier("bad\nname", "postgresql")


class TestSqlName:
    def test_exact_names_are_quoted_with_schema(self):
        assert SqlName("view", "Sales", exact=True).render("postgresql") == '"Sales"."view"'

    def test_import_names_keep_legacy_quoting(self):
        assert SqlName("users").render("postgresql") == "users"
        assert SqlName("order-items").render("mysql") == "`order-items`"


class TestConnectorNameResolver:
    def test_finds_table_in_non_default_schema(self):
        resolver = ConnectorNameResolver(make_adapter({"public": [], "crm": ["Clientes"]}), "o")

        assert resolver.resolve_table(sha("Clientes")) == SqlName("Clientes", "crm", exact=True)

    def test_prefers_default_schema_when_name_repeats(self):
        adapter = make_adapter({"public": ["users"], "archive": ["users"]})

        assert ConnectorNameResolver(adapter, "o").resolve_table(sha("users")).schema == "public"

    def test_ambiguous_outside_default_schema_is_an_error(self):
        adapter = make_adapter({"public": [], "a": ["users"], "b": ["users"]})

        with pytest.raises(MigrationScriptServiceError, match="several schemas"):
            ConnectorNameResolver(adapter, "o").resolve_table(sha("users"))

    def test_unreadable_schema_is_skipped(self):
        adapter = make_adapter({"public": ["t"], "secret": DBQueryExecutionError("denied")})

        assert ConnectorNameResolver(adapter, "o").resolve_table(sha("t")).name == "t"

    def test_column_is_resolved_inside_its_table(self):
        adapter = make_adapter(
            {"public": ["a", "b"]}, columns={("public", "a"): ["id"], ("public", "b"): ["email"]}
        )
        resolver = ConnectorNameResolver(adapter, "o")
        table_a = resolver.resolve_table(sha("a"))

        with pytest.raises(HashNotFoundError):
            resolver.resolve_column(sha("email"), table_a)
        assert resolver.resolve_column(sha("id"), table_a) == SqlName("id", exact=True)

    def test_metadata_is_cached(self):
        adapter = make_adapter({"public": ["a"]}, columns={("public", "a"): ["id"]})
        resolver = ConnectorNameResolver(adapter, "o")
        for _ in range(3):
            table = resolver.resolve_table(sha("a"))
            resolver.resolve_column(sha("id"), table)

        assert adapter.get_tables.call_count == 1
        assert adapter.get_columns.call_count == 1


class TestBuildTablePlans:
    def test_several_origin_tables_for_one_destination_is_an_error(self):
        mappings = [
            {
                "origin_table": "a",
                "origin_column": "x",
                "destination_table": "d",
                "destination_column": "x",
            },
            {
                "origin_table": "b",
                "origin_column": "y",
                "destination_table": "d",
                "destination_column": "y",
            },
        ]

        with pytest.raises(MigrationScriptServiceError, match="several origin tables"):
            MigrationScriptService.build_table_plans(mappings)

    def test_connector_mappings_resolved_with_adapters(self):
        origin = make_adapter({"public": ["Src"]}, columns={("public", "Src"): ["Name"]})
        origin.get_table_statistics.return_value = Mock(row_count=2)
        mappings = [
            {
                "origin_source_type": "connector",
                "origin_table_hash": sha("Src"),
                "origin_column_hash": sha("Name"),
                "destination_table": "dst",
                "destination_column": "name",
            }
        ]

        plans, errors = MigrationScriptService.build_table_plans(mappings, origin_adapter=origin)

        assert errors == []
        assert plans[0].origin == SqlName("Src", "public", exact=True)
        assert plans[0].columns[0].origin == SqlName("Name", exact=True)

        script = MigrationScriptService.generate_insert_script(mappings, origin_adapter=origin)
        assert 'SELECT "Name" FROM "public"."Src";' in script
