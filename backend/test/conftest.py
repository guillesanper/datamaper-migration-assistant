# tests/conftest.py
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Generator

import psycopg2
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from alembic import command
from alembic.config import Config

# ============================================================================
# CARGAR VARIABLES DE ENTORNO
# ============================================================================
# Cargar .env ANTES de cualquier otra importación
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path, encoding="utf-8")

# ============================================================================
# CONFIGURACIÓN DE REDIS PARA TESTS
# ============================================================================
# IMPORTANTE: Configurar variables de entorno ANTES de importar main.app
# para que RedisClient se conecte al Redis de test (puerto 6380)
os.environ["REDIS_HOST"] = "localhost"
os.environ["REDIS_PORT"] = "6380"

# ============================================================================
# CONFIGURACIÓN DE DATABASE PARA TESTS
# ============================================================================
# IMPORTANTE: Configurar variables de entorno ANTES de importar main.app
# para que SessionLocal se conecte a la base de datos de test
os.environ["DB_HOST"] = os.getenv("TEST_DB_HOST", "localhost")
os.environ["DB_PORT"] = os.getenv("TEST_DB_PORT", "5432")
os.environ["DB_USER"] = os.getenv("TEST_DB_USER", "postgres")
os.environ["DB_PASSWORD"] = os.getenv("TEST_DB_PASSWORD", "postgres")
os.environ["DB_NAME"] = "datamap_test"  # Use test database
# Las BDs externas de test (docker-compose.test.yml) escuchan en localhost y sin TLS
os.environ.setdefault("DB_CONNECTOR_ALLOW_PRIVATE_HOSTS", "true")
# Los tests e2e prueban muchas conexiones seguidas con el mismo usuario
os.environ.setdefault("DB_CONNECTOR_RATE_LIMIT", "10000")

from main import app

# ============================================================================
# REDIS RESET FIXTURE
# ============================================================================


@pytest.fixture(scope="session", autouse=True)
def reset_redis_singleton():
    """Resetear el singleton de RedisClient al inicio de la sesión de tests"""
    from app.utils.redis_client import RedisClient

    # Resetear singleton para que use la configuración de test
    if RedisClient._instance is not None:
        try:
            RedisClient._instance.close()
        except:
            pass
        RedisClient._instance = None
        RedisClient._redis = None
        RedisClient._pool = None

    yield

    # Limpiar al final
    if RedisClient._instance is not None:
        try:
            RedisClient._instance.close()
        except:
            pass


# ============================================================================
# PYTEST-XDIST FIXTURES
# ============================================================================


@pytest.fixture(scope="session")
def worker_id(request):
    """
    Obtiene el ID del worker de pytest-xdist.
    Retorna 'master' si no está usando xdist, o 'gw0', 'gw1', etc. si está en paralelo.
    """
    if hasattr(request.config, "workerinput"):
        return request.config.workerinput["workerid"]
    return "master"


def get_unique_user_data(worker_id, base_username="testuser", base_email="test@example.com"):
    """
    Genera datos de usuario únicos por worker para evitar colisiones en pytest-xdist.

    Args:
        worker_id: El worker_id de pytest-xdist
        base_username: Username base (sin sufijo)
        base_email: Email base (sin sufijo)

    Returns:
        tuple: (username, email) con sufijo de worker si es necesario
    """
    if worker_id == "master":
        return base_username, base_email

    # Extraer la parte local del email (antes del @)
    local_part, domain = base_email.split("@")
    unique_email = f"{local_part}_{worker_id}@{domain}"
    unique_username = f"{base_username}_{worker_id}"

    return unique_username, unique_email


# ============================================================================
# DATABASE FIXTURES
# ============================================================================

# Variable global para cachear el estado de la DB
_db_setup_checked = False


def create_worker_database(worker_id: str, config: dict) -> bool:
    """
    Crea una base de datos específica para un worker de pytest-xdist.

    Args:
        worker_id: ID del worker ('master', 'gw0', 'gw1', etc.)
        config: Diccionario con configuración de DB (host, user, password, port)

    Returns:
        bool: True si se creó exitosamente, False en caso contrario
    """
    db_name = f"datamap_test_{worker_id}"

    try:
        # Conectar a BD administrativa (postgres) para crear la BD del worker
        admin_conn = psycopg2.connect(
            host=config["host"],
            database="postgres",
            user=config["user"],
            password=config["password"],
            client_encoding="UTF8",
            options="-c client_encoding=UTF8",
        )
        admin_conn.autocommit = True
        cursor = admin_conn.cursor()

        # Terminar conexiones activas a la BD si existe
        cursor.execute(
            """
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = %s
              AND pid <> pg_backend_pid();
        """,
            (db_name,),
        )

        # DROP si existe
        cursor.execute(f"DROP DATABASE IF EXISTS {db_name}")

        # CREATE nueva BD con encoding UTF8
        cursor.execute(f"""
            CREATE DATABASE {db_name}
            OWNER {config['user']}
            ENCODING 'UTF8'
            LC_COLLATE = 'C'
            LC_CTYPE = 'C'
            TEMPLATE template0
        """)

        cursor.close()
        admin_conn.close()

        # Conectar a la nueva BD para crear extensiones
        worker_conn = psycopg2.connect(
            host=config["host"],
            database=db_name,
            user=config["user"],
            password=config["password"],
            client_encoding="UTF8",
            options="-c client_encoding=UTF8",
        )
        worker_conn.autocommit = True
        cursor = worker_conn.cursor()

        # Crear extensiones
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        cursor.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

        cursor.close()
        worker_conn.close()

        # Aplicar schema usando SQLAlchemy ORM models
        try:
            from urllib.parse import quote_plus

            from sqlalchemy import create_engine

            from app.database.base import Base

            # Importar todos los modelos para que se registren en Base.metadata
            from app.models import orm  # Esto importa todos los modelos ORM

            # Crear engine para esta base de datos con URL-encoding
            db_user = quote_plus(config["user"])
            db_password = quote_plus(config["password"])
            db_url = f"postgresql://{db_user}:{db_password}@{config['host']}:{config.get('port', '5432')}/{db_name}"
            engine = create_engine(
                db_url, echo=False, client_encoding="utf8", connect_args={"client_encoding": "utf8"}
            )

            # Crear todas las tablas desde los modelos ORM (con tipos UUID)
            Base.metadata.create_all(bind=engine)

            # Cerrar engine
            engine.dispose()

            print(f"✓ Base de datos {db_name} creada exitosamente con modelos ORM (UUID)")
            return True

        except Exception as e:
            print(f"❌ Error aplicando schema ORM a {db_name}: {e}")
            import traceback

            traceback.print_exc()
            return False

    except Exception as e:
        print(f"❌ Error creando BD {db_name}: {e}")
        import traceback

        traceback.print_exc()
        return False


def drop_worker_database(worker_id: str, config: dict):
    """
    Elimina la base de datos de un worker.

    Args:
        worker_id: ID del worker ('master', 'gw0', 'gw1', etc.)
        config: Diccionario con configuración de DB
    """
    db_name = f"datamap_test_{worker_id}"

    try:
        admin_conn = psycopg2.connect(
            host=config["host"],
            database="postgres",
            user=config["user"],
            password=config["password"],
            client_encoding="UTF8",
            options="-c client_encoding=UTF8",
        )
        admin_conn.autocommit = True
        cursor = admin_conn.cursor()

        # Terminar conexiones activas
        cursor.execute(
            """
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = %s
              AND pid <> pg_backend_pid();
        """,
            (db_name,),
        )

        # DROP BD
        cursor.execute(f"DROP DATABASE IF EXISTS {db_name}")

        cursor.close()
        admin_conn.close()

        print(f"✓ Base de datos {db_name} eliminada")

    except Exception as e:
        print(f"⚠️  Error eliminando BD {db_name}: {e}")


@pytest.fixture(scope="session", autouse=True)
def setup_worker_databases(worker_id):
    """
    Fixture que crea automáticamente una base de datos específica para cada worker.
    Se ejecuta al inicio de la sesión de tests y limpia al final.
    """
    config = {
        "host": os.getenv("TEST_DB_HOST", os.getenv("DB_HOST", "localhost")),
        "port": os.getenv("TEST_DB_PORT", os.getenv("DB_PORT", "5432")),
        "user": os.getenv("TEST_DB_USER", os.getenv("DB_USER", "postgres")),
        "password": os.getenv("TEST_DB_PASSWORD", os.getenv("DB_PASSWORD", "postgres")),
    }

    print(f"\n🔧 Configurando base de datos para worker: {worker_id}")

    # Crear BD para este worker
    if not create_worker_database(worker_id, config):
        pytest.fail(f"No se pudo crear la base de datos para worker {worker_id}")

    # Configurar SessionLocal para que use la BD del worker
    db_name = f"datamap_test_{worker_id}"
    os.environ["DB_NAME"] = db_name

    # Recrear SessionLocal engine para que use la nueva DB_NAME
    from urllib.parse import quote_plus

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import session as session_module

    # URL-encode the password and user to handle special characters
    # IMPORTANTE: Usar las credenciales de TEST_DB que están en config
    db_user = quote_plus(config["user"])
    db_password = quote_plus(config["password"])
    db_host = config["host"]
    db_port = config.get("port", "5432")

    new_database_url = f"postgresql://{db_user}:{db_password}@" f"{db_host}:{db_port}/{db_name}"

    new_engine = create_engine(
        new_database_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False,
        client_encoding="utf8",  # Importante para Windows
        connect_args={"client_encoding": "utf8", "application_name": f"test_worker_{worker_id}"},
    )

    # Reemplazar el engine y SessionLocal globalmente
    session_module.engine.dispose()  # Cerrar conexiones del engine anterior
    session_module.engine = new_engine
    session_module.SessionLocal = sessionmaker(
        bind=new_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )

    print(f"✓ SessionLocal recreado para usar: {db_name}")

    yield

    # Cleanup: eliminar BD al final de la sesión
    print(f"\n🧹 Limpiando base de datos del worker: {worker_id}")
    drop_worker_database(worker_id, config)


def setup_test_database(worker_id="master"):
    """
    Verifica la base de datos de test para el worker específico.

    Args:
        worker_id: ID del worker ('master', 'gw0', 'gw1', etc.)

    Returns:
        bool: True si la base de datos está lista, False si hay problemas
    """
    global _db_setup_checked

    # Si ya verificamos la DB en esta sesión de Python, no hacer nada
    if _db_setup_checked:
        return True

    db_name = f"datamap_test_{worker_id}"

    try:
        # Verificar si la base de datos existe y tiene tablas
        conn = psycopg2.connect(
            host=os.getenv("TEST_DB_HOST", "localhost"),
            database=db_name,
            user=os.getenv("TEST_DB_USER", "postgres"),
            password=os.getenv("TEST_DB_PASSWORD", "postgres"),
            client_encoding="UTF8",
            options="-c client_encoding=UTF8",
            connect_timeout=5,  # Timeout rápido para detectar problemas
        )

        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM pg_tables
            WHERE schemaname = 'public'
        """)
        table_count = cursor.fetchone()[0]
        cursor.close()
        conn.close()

        # Si hay tablas, la base de datos está lista
        if table_count > 0:
            print(f"✓ Base de datos {db_name} lista ({table_count} tablas)")
            _db_setup_checked = True
            return True
        else:
            print(f"⚠️  Base de datos {db_name} existe pero no tiene tablas")
            return False

    except psycopg2.OperationalError:
        print(f"⚠️  Base de datos {db_name} no encontrada")
        print("   La fixture setup_worker_databases debería crearla automáticamente")
        return False

    return False


@pytest.fixture(scope="session")
def test_db_connection(worker_id, setup_worker_databases):
    """
    Conexión a base de datos de test específica del worker.

    Args:
        worker_id: ID del worker de pytest-xdist
        setup_worker_databases: Fixture que crea la BD del worker (dependencia)

    Yields:
        Connection: Conexión a PostgreSQL para el worker
    """
    # Verificar que la BD del worker esté lista
    if not setup_test_database(worker_id):
        pytest.fail(f"No se pudo inicializar la base de datos para worker {worker_id}")

    db_name = f"datamap_test_{worker_id}"

    conn = psycopg2.connect(
        host=os.getenv("TEST_DB_HOST", "localhost"),
        database=db_name,
        user=os.getenv("TEST_DB_USER", "postgres"),
        password=os.getenv("TEST_DB_PASSWORD", "postgres"),
        client_encoding="UTF8",
        options="-c client_encoding=UTF8",
    )
    conn.autocommit = False
    yield conn
    conn.close()


@pytest.fixture(scope="function")
def db(test_db_connection):
    """Fixture con rollback automático"""
    test_db_connection.rollback()
    yield test_db_connection
    test_db_connection.rollback()


@pytest.fixture(scope="function")
def clean_db(db):
    """Base de datos limpia - usa TRUNCATE optimizado con prepared statement"""
    cursor = db.cursor()

    try:
        # Usar TRUNCATE con RESTART IDENTITY para resetear secuencias más rápido
        # Solo truncar las tablas que probablemente tengan datos
        cursor.execute("""
            TRUNCATE TABLE
                comment_reactions, comment_reads, comments, entity_locks,
                notifications, project_activity, version_tags, entity_versions,
                mappings, primary_key_constraints, columns, tables,
                project_members, project_encryption, subscriptions,
                project_metrics_history, projects,
                email_otps, user_sessions, csrf_tokens, security_logs,
                security_rate_limits, user_preferences, user_api_keys, users
            RESTART IDENTITY CASCADE
        """)
        db.commit()
    except Exception as e:
        db.rollback()
        # Si TRUNCATE falla (ej: tabla no existe), usar DELETE más simple
        # Desactivar triggers temporalmente para mayor velocidad
        cursor.execute("SET session_replication_role = replica;")

        # Orden de eliminación respetando foreign keys
        tables = [
            "comment_reactions",
            "comment_reads",
            "comments",
            "entity_locks",
            "notifications",
            "project_activity",
            "version_tags",
            "entity_versions",
            "mappings",
            "primary_key_constraints",
            "columns",
            "tables",
            "project_members",
            "project_encryption",
            "subscriptions",
            "subscription_plans",
            "project_metrics_history",
            "projects",
            "email_otps",
            "user_sessions",
            "csrf_tokens",
            "security_logs",
            "security_rate_limits",
            "user_preferences",
            "user_api_keys",
            "users",
        ]

        for table in tables:
            try:
                cursor.execute(f"DELETE FROM {table}")
            except:
                pass  # Ignorar si la tabla no existe

        cursor.execute("SET session_replication_role = DEFAULT;")
        db.commit()
    finally:
        cursor.close()

    return db


# ============================================================================
# REDIS FIXTURES
# ============================================================================


@pytest.fixture(scope="function")
def fake_redis():
    """Fake Redis para tests"""
    import fakeredis

    # decode_responses=True para que coincida con el cliente real
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    yield redis_client
    redis_client.flushall()


@pytest.fixture(scope="function")
def mock_redis_cache(fake_redis):
    """Mock de RedisEncryptionSessionCache usando fakeredis"""
    from unittest.mock import patch

    from app.utils.redis_session_cache import RedisEncryptionSessionCache

    # Patch get_redis_client para que devuelva fake_redis directamente
    with patch("app.utils.redis_session_cache.get_redis_client") as mock_get_client:
        mock_get_client.return_value = fake_redis
        cache = RedisEncryptionSessionCache()
        yield cache


# ============================================================================
# API CLIENT FIXTURES
# ============================================================================


class ConnectionWrapper:
    """Wrapper para conexión de DB que permite commits pero ignora close()"""

    def __init__(self, real_connection):
        self._real_connection = real_connection

    def __getattr__(self, name):
        # Interceptar solo close() para no cerrar la conexión de test
        if name == "close":
            return lambda: None  # No hacer nada
        # PERMITIR commit() - los fixtures db y clean_db hacen rollback al final
        return getattr(self._real_connection, name)


@pytest.fixture(scope="function")
def client(test_db_connection, setup_worker_databases):
    """Cliente de test para FastAPI con DB override - OPTIMIZADO"""
    from unittest.mock import patch

    import fakeredis
    from fastapi import Response

    from app.database import session as session_module
    from app.database.database import get_db
    from app.database.session import get_db_session

    # Rollback cualquier transacción fallida antes de empezar
    try:
        test_db_connection.rollback()
    except:
        pass

    # Guardar set_cookie original
    original_set_cookie = Response.set_cookie

    # Wrapper para set_cookie que fuerza secure=False en tests
    def test_set_cookie(self, *args, **kwargs):
        kwargs["secure"] = False
        return original_set_cookie(self, *args, **kwargs)

    # Parchear Response.set_cookie
    Response.set_cookie = test_set_cookie

    # Mock get_db que devuelve un wrapper de la conexión de test
    def mock_get_db():
        return ConnectionWrapper(test_db_connection)

    # Override del dependency para FastAPI
    def override_get_db():
        try:
            yield test_db_connection
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # Override de get_db_session para SQLAlchemy Session
    def override_get_db_session():
        session = session_module.SessionLocal()
        try:
            yield session
        finally:
            session.rollback()
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db_session

    # Crear FakeRedis para tests con decode_responses=True (igual que el cliente real)
    fake_redis_client = fakeredis.FakeRedis(decode_responses=True)

    # Mock para get_redis_client que devuelve FakeRedis directamente
    def mock_get_redis_client():
        return fake_redis_client

    # Parchear get_db y Redis globalmente usando unittest.mock
    with (
        patch("app.database.database.get_db", mock_get_db),
        patch("app.utils.security_logger.get_db", mock_get_db),
        patch("app.middleware.rate_limiting.get_db", mock_get_db),
        patch("app.middleware.csrf_protection.get_db", mock_get_db),
        patch("app.utils.redis_client.get_redis_client", mock_get_redis_client),
        patch("app.utils.redis_session_cache.get_redis_client", mock_get_redis_client),
    ):

        with TestClient(app) as c:
            yield c

    # Restaurar set_cookie original
    Response.set_cookie = original_set_cookie

    # Limpiar override
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db_session, worker_id):
    """Usuario de prueba verificado - único por worker para pytest-xdist"""
    from app.models.orm import User
    from app.services.auth_service import AuthService

    # Usar worker_id para crear usuarios únicos por worker (evita race conditions en xdist)
    # worker_id será 'master' en modo single-threaded, o 'gw0', 'gw1', etc. en xdist
    if worker_id == "master":
        suffix = ""
    else:
        suffix = f"_{worker_id}"

    email = f"test{suffix}@example.com"
    username = f"testuser{suffix}"
    password = "Test123!@#"

    try:
        # Intentar obtener usuario existente primero usando SQLAlchemy
        existing_user = db_session.query(User).filter(User.email == email).first()

        if existing_user:
            # Si el usuario ya existe, solo asegurarse de que está verificado
            existing_user.is_verified = True
            db_session.commit()

            return {
                "id": str(existing_user.id),
                "username": username,
                "email": email,
                "password": password,
            }

        # Si no existe, crear el usuario usando AuthService con SQLAlchemy Session
        auth_service = AuthService(db_session)
        user = auth_service.create_user(username=username, email=email, password=password)

        # Marcar como verificado usando SQLAlchemy
        created_user = db_session.query(User).filter(User.id == user["user_id"]).first()
        if created_user:
            created_user.is_verified = True
            db_session.commit()

        return {"id": user["user_id"], "username": username, "email": email, "password": password}
    except Exception as e:
        # En caso de error, hacer rollback y re-lanzar
        db_session.rollback()
        raise


@pytest.fixture
def authenticated_client(client, test_user):
    """Cliente autenticado con cookie de sesión"""
    response = client.post(
        "/api/auth/login",
        json={"identifier": test_user["email"], "password": test_user["password"]},
    )

    assert response.status_code == 200, f"Login failed: {response.json()}"
    assert "session" in response.cookies, "Session cookie not set"

    # La autenticación se maneja via cookies, TestClient las guarda automáticamente
    return client


@pytest.fixture
def test_project(db_session, test_user):
    """Proyecto de prueba - usa SQLAlchemy session (ORM)"""
    from app.crud.project_crud import ProjectCRUD

    return ProjectCRUD.create_project_orm(
        db=db_session,
        owner_id=test_user["id"],
        name="Test Project",
        description="A test project",
        origin_db="PostgreSQL",
        destination_db="MySQL",
        status="active",
    )


@pytest.fixture
def db_session(setup_worker_databases):
    """
    SQLAlchemy Session for ORM tests.

    Este fixture proporciona una sesión de SQLAlchemy que usa el SessionLocal
    recreado para el worker específico. Depende de setup_worker_databases para
    asegurar que el engine y SessionLocal estén correctamente configurados.

    Yields:
        Session: SQLAlchemy session for the test
    """
    # Importar dinámicamente para obtener el SessionLocal actualizado
    from app.database import session as session_module

    session = session_module.SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="function")
def clean_db_session(setup_worker_databases):
    """
    SQLAlchemy Session for ORM tests with clean database.

    Similar to clean_db but uses SQLAlchemy Session instead of psycopg2 connection.
    Truncates all tables before yielding the session.

    Yields:
        Session: SQLAlchemy session with clean database
    """
    from sqlalchemy import text

    from app.database import session as session_module

    session = session_module.SessionLocal()

    try:
        # TRUNCATE all tables using raw SQL through SQLAlchemy
        session.execute(text("""
            TRUNCATE TABLE
                comment_reactions, comment_reads, comments, entity_locks,
                notifications, project_activity, version_tags, entity_versions,
                mappings, primary_key_constraints, columns, tables,
                project_members, project_encryption, subscriptions,
                project_metrics_history, projects,
                email_otps, user_sessions, csrf_tokens, security_logs,
                security_rate_limits, user_preferences, user_api_keys, users
            RESTART IDENTITY CASCADE
        """))
        session.commit()
    except Exception:
        session.rollback()
        # Fallback: delete from each table individually
        tables = [
            "comment_reactions",
            "comment_reads",
            "comments",
            "entity_locks",
            "notifications",
            "project_activity",
            "version_tags",
            "entity_versions",
            "mappings",
            "primary_key_constraints",
            "columns",
            "tables",
            "project_members",
            "project_encryption",
            "subscriptions",
            "subscription_plans",
            "project_metrics_history",
            "projects",
            "email_otps",
            "user_sessions",
            "csrf_tokens",
            "security_logs",
            "security_rate_limits",
            "user_preferences",
            "user_api_keys",
            "users",
        ]
        for table in tables:
            try:
                session.execute(text(f"DELETE FROM {table}"))
            except Exception:
                pass
        session.commit()

    try:
        yield session
    finally:
        session.rollback()
        session.close()
