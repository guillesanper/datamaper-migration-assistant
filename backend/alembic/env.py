import os
import sys
from logging.config import fileConfig
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import engine_from_config, pool

from alembic import context

# Agregar el directorio backend al path para poder importar los modelos
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# Cargar variables de entorno
from dotenv import load_dotenv

load_dotenv(encoding="utf-8")

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Configurar la URL de SQLAlchemy dinámicamente desde variables de entorno
if not config.get_main_option("sqlalchemy.url"):
    database_url = (
        f"postgresql://{quote_plus(os.getenv('DB_USER', ''))}:"
        f"{quote_plus(os.getenv('DB_PASSWORD', ''))}@"
        f"{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )
    # "%" se escapa porque configparser lo interpreta como interpolación
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Importar Base y todos los modelos ORM para autogenerate
from app.database.base import Base
from app.models import orm  # Esto importa todos los modelos definidos en orm/__init__.py

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # Detectar cambios en tipos de columnas
        compare_server_default=True,  # Detectar cambios en valores por defecto
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # Detectar cambios en tipos de columnas
            compare_server_default=True,  # Detectar cambios en valores por defecto
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
