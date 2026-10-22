"""
Unit tests for BaseDBAdapter.get_full_schema_metadata (implementación genérica tabla a tabla,
la que usan MySQL, SQL Server y Oracle).
"""

from typing import List, Optional

from app.models.db_metadata import (
    ColumnMetadata,
    DataType,
    ForeignKeyMetadata,
    IndexMetadata,
    PrimaryKeyMetadata,
    TableMetadata,
    TableStatistics,
    UniqueConstraintMetadata,
)
from app.utils.db_adapters.base_adapter import BaseDBAdapter
from app.utils.db_adapters.exceptions import DBMetadataNotFoundError


class FakeAdapter(BaseDBAdapter):
    """Adapter en memoria que registra las llamadas (table_name, schema)."""

    def __init__(self):
        super().__init__({"host": "h", "port": 1, "database": "db", "user": "u", "password": "p"})
        self.calls: List[tuple] = []

    @property
    def dialect(self) -> str:
        return "fake"

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def test_connection(self) -> bool:
        return True

    def get_schemas(self) -> List[str]:
        return ["app"]

    def _get_default_schema(self) -> str:
        return "app"

    def get_tables(self, schema: Optional[str] = None) -> List[TableMetadata]:
        return [
            TableMetadata(name="orders", schema=schema),
            TableMetadata(name="hidden", schema=schema),
        ]

    def get_columns(self, table_name: str, schema: Optional[str] = None):
        self.calls.append(("columns", table_name, schema))
        if table_name == "hidden":
            # p. ej. sin permisos sobre las columnas
            raise DBMetadataNotFoundError("no columns")
        return [
            ColumnMetadata(
                name="id", data_type=DataType.INTEGER, native_type="INT", ordinal_position=1
            ),
            ColumnMetadata(
                name="customer_id",
                data_type=DataType.INTEGER,
                native_type="INT",
                ordinal_position=2,
            ),
        ]

    def get_primary_keys(self, table_name: str, schema: Optional[str] = None):
        self.calls.append(("pks", table_name, schema))
        if table_name != "orders":
            return []
        return [
            PrimaryKeyMetadata(
                constraint_name="orders_pk", column_names=["id"], table_name=table_name
            )
        ]

    def get_foreign_keys(self, table_name: str, schema: Optional[str] = None):
        self.calls.append(("fks", table_name, schema))
        if table_name != "orders":
            return []
        return [
            ForeignKeyMetadata(
                constraint_name="orders_customer_fk",
                column_names=["customer_id"],
                referenced_table="customers",
                referenced_columns=["id"],
                table_name=table_name,
            )
        ]

    def get_unique_constraints(self, table_name: str, schema: Optional[str] = None):
        self.calls.append(("uniques", table_name, schema))
        return (
            []
            if table_name != "orders"
            else [
                UniqueConstraintMetadata(
                    constraint_name="orders_uq", column_names=["customer_id"], table_name=table_name
                )
            ]
        )

    def get_indexes(self, table_name: str, schema: Optional[str] = None):
        self.calls.append(("indexes", table_name, schema))
        return (
            []
            if table_name != "orders"
            else [IndexMetadata(name="orders_idx", columns=["customer_id"], table_name=table_name)]
        )

    def get_table_statistics(self, table_name: str, schema: Optional[str] = None):
        return TableStatistics(table_name=table_name, row_count=0, size_bytes=0)


def test_calls_use_table_then_schema_order():
    adapter = FakeAdapter()
    adapter.get_full_schema_metadata("app")

    assert all(call[1] in {"orders", "hidden"} and call[2] == "app" for call in adapter.calls)


def test_default_schema_is_resolved_once():
    adapter = FakeAdapter()
    metadata = adapter.get_full_schema_metadata()

    assert metadata.name == "app"
    assert all(call[2] == "app" for call in adapter.calls)


def test_collects_constraints_and_marks_key_columns():
    metadata = FakeAdapter().get_full_schema_metadata("app")

    assert [pk.name for pk in metadata.primary_keys] == ["orders_pk"]
    assert [fk.name for fk in metadata.foreign_keys] == ["orders_customer_fk"]
    assert [u.name for u in metadata.unique_constraints] == ["orders_uq"]
    assert [i.name for i in metadata.indexes] == ["orders_idx"]

    orders = metadata.get_table("orders")
    assert orders.get_column("id").is_primary_key
    assert orders.get_column("customer_id").is_foreign_key


def test_table_without_visible_columns_does_not_break_schema():
    metadata = FakeAdapter().get_full_schema_metadata("app")

    assert {t.name for t in metadata.tables} == {"orders", "hidden"}
    assert metadata.get_table("hidden").columns == []
