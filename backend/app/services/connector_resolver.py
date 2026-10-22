"""
Connector Name Resolver

Resuelve los hashes SHA-256 de los mappings en modo connector a nombres reales
consultando la metadata de la BD externa, y representa los nombres resultantes.

Los hashes solo contienen el nombre (sin schema ni tabla), así que una tabla se busca
en todos los schemas visibles (primero el schema por defecto) y una columna solo
dentro de la tabla ya resuelta.
"""

import hashlib
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.utils.db_adapters.base_adapter import BaseDBAdapter
from app.utils.db_adapters.exceptions import DBAdapterError
from app.utils.sql_safety import quote_exact_identifier, quote_identifier

logger = logging.getLogger(__name__)


class MigrationScriptServiceError(Exception):
    """Base exception for MigrationScriptService"""

    pass


class HashNotFoundError(MigrationScriptServiceError):
    """Hash no se encontró en la base de datos"""

    def __init__(self, hash_value: str, side: str):
        self.hash_value = hash_value
        self.side = side
        super().__init__(
            f"Hash {hash_value[:8]}... not found in {side} database. "
            f"Table/column may have been renamed or deleted."
        )


def name_hash(name: str) -> str:
    """Hash con el que /connector-tables identifica tablas y columnas."""
    return hashlib.sha256(name.encode()).hexdigest()


@dataclass(frozen=True)
class SqlName:
    """
    Nombre de tabla (opcionalmente con schema) o de columna.

    exact=True indica que el nombre se leyó del catálogo de la BD: se cita siempre
    tal cual (respeta mayúsculas, palabras reservadas y puntos dentro del nombre).
    Los nombres de mappings en modo import los escribe el usuario y conservan el
    comportamiento de quote_identifier (sin citar si es un identificador simple).
    """

    name: str
    schema: Optional[str] = None
    exact: bool = False

    def render(self, dialect: str) -> str:
        if not self.exact:
            full = f"{self.schema}.{self.name}" if self.schema else self.name
            return quote_identifier(full, dialect)
        parts = [self.schema, self.name] if self.schema else [self.name]
        return ".".join(quote_exact_identifier(part, dialect) for part in parts)

    def __str__(self) -> str:
        return f"{self.schema}.{self.name}" if self.schema else self.name


class ConnectorNameResolver:
    """Resuelve hashes de tablas y columnas contra un adapter conectado (con caché)."""

    def __init__(self, adapter: BaseDBAdapter, side: str):
        self.adapter = adapter
        self.side = side
        self._tables_by_hash: Optional[Dict[str, List[SqlName]]] = None
        self._columns: Dict[SqlName, List[str]] = {}

    def _load_tables(self) -> Dict[str, List[SqlName]]:
        if self._tables_by_hash is not None:
            return self._tables_by_hash

        default_schema = self.adapter._get_default_schema()
        schemas = [default_schema] + [s for s in self.adapter.get_schemas() if s != default_schema]

        tables_by_hash: Dict[str, List[SqlName]] = {}
        for schema in schemas:
            try:
                tables = self.adapter.get_tables(schema)
            except DBAdapterError as e:
                # Un schema ilegible (permisos) no impide resolver el resto
                logger.warning(f"Cannot list tables of schema '{schema}' ({self.side}): {e}")
                continue
            for table in tables:
                ref = SqlName(name=table.name, schema=table.schema or schema, exact=True)
                tables_by_hash.setdefault(name_hash(table.name), []).append(ref)

        self._tables_by_hash = tables_by_hash
        return tables_by_hash

    def resolve_table(self, hash_value: str) -> SqlName:
        candidates = self._load_tables().get(hash_value, [])
        if not candidates:
            raise HashNotFoundError(hash_value, self.side)

        if len(candidates) > 1:
            default_schema = self.adapter._get_default_schema()
            in_default = [c for c in candidates if c.schema == default_schema]
            if len(in_default) != 1:
                raise MigrationScriptServiceError(
                    f"Table '{candidates[0].name}' exists in several schemas of the "
                    f"{self.side} database ({', '.join(str(c.schema) for c in candidates)}); "
                    f"cannot tell which one the mapping refers to"
                )
            return in_default[0]

        return candidates[0]

    def resolve_column(self, hash_value: str, table: SqlName) -> SqlName:
        if table not in self._columns:
            columns = self.adapter.get_columns(table.name, table.schema)
            self._columns[table] = [column.name for column in columns]

        for column_name in self._columns[table]:
            if name_hash(column_name) == hash_value:
                return SqlName(name=column_name, exact=True)

        raise HashNotFoundError(hash_value, self.side)
