#!/usr/bin/env python3
"""
Script para inicializar la base de datos de test.
Ejecuta los scripts SQL necesarios para crear la estructura de la BD.
Usa psql en lugar de psycopg2 para evitar problemas de encoding.
"""

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

# Cargar variables de entorno desde .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, encoding="utf-8")

# Configurar encoding de salida en Windows
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def get_db_config():
    """Obtiene configuración de base de datos desde variables de entorno"""
    return {
        "host": os.getenv("TEST_DB_HOST", "localhost"),
        "port": os.getenv("TEST_DB_PORT", "5432"),
        "user": os.getenv("TEST_DB_USER", "postgres"),
        "password": os.getenv("TEST_DB_PASSWORD", "postgres"),
    }


def run_psql_command(sql_command, dbname="postgres", config=None):
    """Ejecuta un comando SQL usando psql"""
    if config is None:
        config = get_db_config()

    cmd = [
        "psql",
        "-h",
        config["host"],
        "-p",
        config["port"],
        "-U",
        config["user"],
        "-d",
        dbname,
        "-c",
        sql_command,
    ]

    env = os.environ.copy()
    env["PGPASSWORD"] = config["password"]
    env["PGCLIENTENCODING"] = "UTF8"

    result = subprocess.run(cmd, env=env, capture_output=True, encoding="utf-8", errors="replace")

    return result


def run_psql_file(sql_file, dbname="datamap_test", config=None):
    """Ejecuta un archivo SQL usando psql - convierte UTF-16 a UTF-8 si es necesario"""
    if config is None:
        config = get_db_config()

    # Detectar y convertir el archivo si está en UTF-16
    temp_file = None
    try:
        # Intentar leer como UTF-16
        with open(sql_file, "r", encoding="utf-16") as f:
            content = f.read()

        # Crear archivo temporal en UTF-8
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".sql", delete=False
        ) as tmp:
            tmp.write(content)
            temp_file = tmp.name

        sql_file_to_use = temp_file
        print(f"  Archivo convertido de UTF-16 a UTF-8")
    except UnicodeDecodeError:
        # El archivo ya está en UTF-8 u otro encoding
        sql_file_to_use = sql_file

    try:
        cmd = [
            "psql",
            "-h",
            config["host"],
            "-p",
            config["port"],
            "-U",
            config["user"],
            "-d",
            dbname,
            "-f",
            sql_file_to_use,
        ]

        env = os.environ.copy()
        env["PGPASSWORD"] = config["password"]
        env["PGCLIENTENCODING"] = "UTF8"

        result = subprocess.run(
            cmd, env=env, capture_output=True, encoding="utf-8", errors="replace"
        )

        return result
    finally:
        # Limpiar archivo temporal si se creó
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except:
                pass


def create_test_database():
    """Crea la base de datos de test y aplica el schema"""

    try:
        config = get_db_config()

        # Mostrar configuración
        print(f"Configuracion:")
        print(f"  Host: {config['host']}")
        print(f"  Port: {config['port']}")
        print(f"  User: {config['user']}")
        print()

        # Verificar que psql esté disponible
        try:
            subprocess.run(["psql", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("[ERROR] psql no encontrado. Por favor instala PostgreSQL client tools.")
            print("        En Windows: asegurate de que psql.exe este en el PATH")
            return False

        print("Conectando a PostgreSQL...")

        # Verificar si la BD de test existe
        result = run_psql_command(
            "SELECT 1 FROM pg_database WHERE datname = 'datamap_test'", "postgres", config
        )

        if result.returncode != 0:
            print(f"[ERROR] No se pudo conectar a PostgreSQL: {result.stderr}")
            return False

        print("[OK] Conexion exitosa")

        # Si la BD existe, eliminarla
        if "SELECT 1" in result.stdout or "(1 row)" in result.stdout:
            print("Base de datos 'datamap_test' ya existe. Eliminando...")

            # Terminar conexiones activas
            run_psql_command(
                """
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = 'datamap_test'
                  AND pid <> pg_backend_pid();
                """,
                "postgres",
                config,
            )

            # Eliminar BD
            result = run_psql_command("DROP DATABASE datamap_test", "postgres", config)
            if result.returncode != 0:
                print(f"[ERROR] No se pudo eliminar la base de datos: {result.stderr}")
                return False

            print("[OK] Base de datos eliminada")

        # Crear BD de test
        print("Creando base de datos 'datamap_test'...")
        result = run_psql_command(
            """
            CREATE DATABASE datamap_test
            OWNER postgres
            ENCODING 'UTF8'
            LC_COLLATE = 'C'
            LC_CTYPE = 'C'
            TEMPLATE template0;
            """,
            "postgres",
            config,
        )

        if result.returncode != 0:
            print(f"[ERROR] No se pudo crear la base de datos: {result.stderr}")
            return False

        print("[OK] Base de datos creada exitosamente")

        # Crear extensiones
        print("Creando extensiones...")

        result = run_psql_command("CREATE EXTENSION IF NOT EXISTS pgcrypto", "datamap_test", config)
        if result.returncode != 0:
            print(f"[WARNING] Error creando pgcrypto: {result.stderr}")

        result = run_psql_command(
            'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"', "datamap_test", config
        )
        if result.returncode != 0:
            print(f"[WARNING] Error creando uuid-ossp: {result.stderr}")

        print("[OK] Extensiones creadas")

        # Aplicar schema usando Alembic migrations
        print("Aplicando schema usando Alembic migrations...")
        try:
            from alembic import command
            from alembic.config import Config as AlembicConfig

            # Create an Alembic config object programmatically
            alembic_cfg = AlembicConfig()

            # Set the script location (relative to backend directory)
            backend_dir = Path(__file__).parent.parent
            alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))

            # Configure the database URL
            db_url = f"postgresql://{config['user']}:{config['password']}@{config['host']}:{config['port']}/datamap_test"
            alembic_cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))

            # Suppress Alembic output during setup
            alembic_cfg.set_main_option("sqlalchemy.echo", "false")

            # Run the migrations to HEAD
            command.upgrade(alembic_cfg, "head")

            print("[OK] Alembic migrations aplicadas exitosamente")

        except Exception as e:
            print(f"[ERROR] Error aplicando migraciones Alembic: {e}")
            import traceback

            traceback.print_exc()
            return False

        print("\n[OK] Base de datos de test inicializada correctamente!")
        return True

    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = create_test_database()
    sys.exit(0 if success else 1)
