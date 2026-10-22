"""Unit tests for the cross-database copy SQL and migration router helpers."""

from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.models.db_connection import DBConnectionConfig
from app.routers.migration import ensure_mappings_decrypted, is_cross_database
from app.services.connector_resolver import SqlName
from app.services.data_copy_service import COPY_PLAN_MARKER, DataCopyService
from app.services.migration_script_service import ColumnPlan, TablePlan
from app.utils.sql_safety import UnsafeSQLError


def adapter(dialect):
    return Mock(dialect=dialect)


PLAN = TablePlan(
    origin=SqlName("Clientes", "crm", exact=True),
    dest=SqlName("clients"),
    columns=[
        ColumnPlan(SqlName("Nombre", exact=True), SqlName("name"), "UPPER({column})"),
        ColumnPlan(SqlName("age", exact=True), SqlName("age"), None, "VARCHAR", "INTEGER"),
    ],
)


class TestCopySql:
    def test_select_uses_origin_dialect_and_transformation(self):
        service = DataCopyService(adapter("mysql"), adapter("postgresql"))

        assert service.build_select(PLAN) == "SELECT UPPER(`Nombre`), `age` FROM `crm`.`Clientes`"

    @pytest.mark.parametrize(
        "dialect,values",
        [
            ("postgresql", "%s, CAST(%s AS INTEGER)"),
            ("mysql", "%s, CAST(%s AS INTEGER)"),
            ("sqlserver", "?, CAST(? AS INTEGER)"),
            ("oracle", ":1, CAST(:2 AS INTEGER)"),
        ],
    )
    def test_insert_is_parametrized_per_driver(self, dialect, values):
        service = DataCopyService(adapter("postgresql"), adapter(dialect))

        assert service.build_insert(PLAN).endswith(f"VALUES ({values})")

    def test_transformation_with_extra_statement_is_rejected(self):
        plan = TablePlan(
            origin=SqlName("t"),
            dest=SqlName("d"),
            columns=[ColumnPlan(SqlName("c"), SqlName("c"), "1; DROP TABLE users")],
        )

        with pytest.raises(UnsafeSQLError):
            DataCopyService(adapter("postgresql"), adapter("postgresql")).build_select(plan)

    def test_invalid_destination_type_is_rejected(self):
        plan = TablePlan(
            origin=SqlName("t"),
            dest=SqlName("d"),
            columns=[ColumnPlan(SqlName("c"), SqlName("c"), None, "TEXT", "INT); DROP")],
        )

        with pytest.raises(UnsafeSQLError):
            DataCopyService(adapter("postgresql"), adapter("postgresql")).build_insert(plan)

    def test_describe_marks_plan_and_comments_every_line(self):
        text = DataCopyService(adapter("mysql"), adapter("postgresql")).describe(
            [PLAN], project_name="P\nDROP TABLE x"
        )

        assert text.startswith(COPY_PLAN_MARKER)
        assert all(line.startswith("--") for line in text.splitlines() if line)


def config(**overrides):
    values = dict(
        dialect="postgresql",
        host="db.example.com",
        port=5432,
        database="app",
        user="u",
        password="p",
    )
    values.update(overrides)
    return DBConnectionConfig(**values)


class TestIsCrossDatabase:
    def test_same_session_is_same_database(self):
        assert not is_cross_database("s", "s", config(), config(database="other"))

    def test_same_server_and_database_with_other_user(self):
        assert not is_cross_database("a", "b", config(user="reader"), config(host="DB.example.com"))

    @pytest.mark.parametrize(
        "change", [{"database": "crm"}, {"host": "other"}, {"port": 5433}, {"dialect": "mysql"}]
    )
    def test_different_databases(self, change):
        assert is_cross_database("a", "b", config(), config(**change))

    def test_without_origin_is_not_cross(self):
        assert not is_cross_database(None, "b", None, config())


class TestEnsureMappingsDecrypted:
    def test_encrypted_transformation_without_key_is_locked(self):
        with pytest.raises(HTTPException) as exc:
            ensure_mappings_decrypted(
                [{"transformation_logic_encrypted": "x", "origin_table": "t"}]
            )
        assert exc.value.status_code == 423

    def test_decrypted_mappings_pass(self):
        ensure_mappings_decrypted(
            [
                {
                    "origin_table_encrypted": "x",
                    "origin_table": "t",
                    "transformation_logic_encrypted": "y",
                    "transformation_logic": "UPPER({column})",
                }
            ]
        )

    def test_connector_side_does_not_need_names(self):
        ensure_mappings_decrypted(
            [{"origin_source_type": "connector", "origin_table_encrypted": "stale"}]
        )
