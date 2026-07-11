"""
SQLAlchemy Declarative Base

Este módulo define la clase base para todos los modelos ORM de SQLAlchemy.
Incluye convenciones de nombres para constraints (PKs, FKs, índices, etc.)
que facilitan la gestión de migraciones con Alembic.

Convenciones de nombres:
- ix: Índices -> ix_<nombre_columna>
- uq: Unique constraints -> uq_<nombre_tabla>_<nombre_columna>
- ck: Check constraints -> ck_<nombre_tabla>_<nombre_constraint>
- fk: Foreign keys -> fk_<tabla_origen>_<columna>_<tabla_destino>
- pk: Primary keys -> pk_<nombre_tabla>
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Convenciones de nombres para constraints
# Esto ayuda a Alembic a generar nombres consistentes y predecibles
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=convention)


class Base(DeclarativeBase):
    """
    Clase base para todos los modelos ORM de SQLAlchemy.

    Todos los modelos de la aplicación deben heredar de esta clase.

    Ejemplo:
        class User(Base):
            __tablename__ = "users"

            id = Column(UUID(as_uuid=True), primary_key=True)
            username = Column(String(50), nullable=False)
    """

    metadata = metadata
