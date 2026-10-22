"""
E2E Test Fixtures for Database Connections

Fixtures adicionales específicas para tests e2e del router de conexiones a BD.
"""

import os

import pytest
import redis

from app.services.auth_service import AuthService

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


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
# REDIS FIXTURES
# ============================================================================


@pytest.fixture(scope="function")
def redis_test_client():
    """FakeRedis client for E2E tests"""
    import fakeredis

    # decode_responses=False para que coincida con el cliente real de sessions
    client = fakeredis.FakeRedis(decode_responses=False)
    yield client
    client.flushall()


@pytest.fixture(scope="function")
def clean_redis(redis_test_client):
    """Redis limpio antes de cada test"""
    redis_test_client.flushdb()
    yield redis_test_client
    redis_test_client.flushdb()


# ============================================================================
# USER FIXTURES
# ============================================================================


@pytest.fixture
def second_test_user(db_session, worker_id):
    """Segundo usuario para tests de ownership y multi-usuario - único por worker"""
    from app.models.orm import User
    from app.services.auth_service import AuthService

    # Usar worker_id para crear usuarios únicos por worker
    if worker_id == "master":
        suffix = ""
    else:
        suffix = f"_{worker_id}"

    email = f"test2_e2e{suffix}@example.com"
    username = f"testuser2_e2e{suffix}"
    password = "Test123!@#"

    try:
        # Intentar obtener usuario existente primero usando SQLAlchemy
        existing_user = db_session.query(User).filter(User.email == email).first()

        if existing_user:
            # Si existe, solo asegurar que está verificado
            existing_user.is_verified = True
            db_session.commit()

            return {
                "id": str(existing_user.id),
                "username": username,
                "email": email,
                "password": password,
            }

        # Si no existe, crear el usuario
        auth_service = AuthService(db_session)
        user = auth_service.create_user(username=username, email=email, password=password)

        # Marcar como verificado
        created_user = db_session.query(User).filter(User.id == user["user_id"]).first()
        if created_user:
            created_user.is_verified = True
            db_session.commit()

        return {"id": user["user_id"], "username": username, "email": email, "password": password}
    except Exception as e:
        db_session.rollback()
        raise


@pytest.fixture(scope="function")
def test_environment_setup(test_db_connection, clean_redis):
    """Setup compartido para múltiples clientes autenticados en el mismo test - OPTIMIZADO"""
    from unittest.mock import patch

    from fastapi import Response

    from app.database.database import get_db
    from app.routers.db_connections import get_redis_client
    from main import app

    # Guardar set_cookie original
    original_set_cookie = Response.set_cookie

    # Wrapper para set_cookie que fuerza secure=False en tests
    def test_set_cookie(self, *args, **kwargs):
        kwargs["secure"] = False
        return original_set_cookie(self, *args, **kwargs)

    Response.set_cookie = test_set_cookie

    # Mock get_db con wrapper que permite commits pero bloquea close
    class ConnectionWrapper:
        """Wrapper para conexión de DB que ignora close() durante tests"""

        def __init__(self, connection):
            self._connection = connection

        def __getattr__(self, name):
            if name == "close":
                return lambda: None
            return getattr(self._connection, name)

    def mock_get_db():
        return ConnectionWrapper(test_db_connection)

    def override_get_db():
        try:
            yield ConnectionWrapper(test_db_connection)
        finally:
            pass

    # Mock para get_redis_client
    def mock_get_redis_client():
        return clean_redis

    # Override de dependencies de FastAPI
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_client] = lambda: clean_redis

    # Parchear todas las referencias - el contexto se mantendrá durante TODO el test
    with (
        patch("app.database.database.get_db", mock_get_db),
        patch("app.utils.security_logger.get_db", mock_get_db),
        patch("app.middleware.rate_limiting.get_db", mock_get_db),
        patch("app.middleware.csrf_protection.get_db", mock_get_db),
        patch("app.utils.redis_client.get_redis_client", mock_get_redis_client),
        patch("app.utils.redis_session_cache.get_redis_client", mock_get_redis_client),
    ):

        yield {"app": app, "db": test_db_connection, "redis": clean_redis}

    # Restaurar al final del test
    Response.set_cookie = original_set_cookie
    app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client_with_redis(test_environment_setup, worker_id):
    """Cliente autenticado con el environment setup compartido - único por worker"""
    from fastapi.testclient import TestClient

    from app.services.auth_service import AuthService

    app = test_environment_setup["app"]
    test_db_connection = test_environment_setup["db"]

    # Rollback cualquier transacción fallida antes de empezar
    try:
        test_db_connection.rollback()
    except:
        pass

    # Usar worker_id para crear usuarios únicos por worker
    if worker_id == "master":
        suffix = ""
    else:
        suffix = f"_{worker_id}"

    email = f"test_e2e{suffix}@example.com"
    username = f"testuser_e2e{suffix}"
    password = "Test123!@#"

    try:
        # Intentar obtener usuario existente primero
        cursor = test_db_connection.cursor()
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            # Si existe, solo asegurar que está verificado
            user_id = existing_user[0]
            cursor.execute("UPDATE users SET is_verified = TRUE WHERE id = %s", (user_id,))
            test_db_connection.commit()
            cursor.close()
        else:
            cursor.close()
            # Si no existe, crear el usuario usando SQLAlchemy Session
            from app.database.session import SessionLocal

            with SessionLocal() as session:
                auth_service = AuthService(session)
                user = auth_service.create_user(username=username, email=email, password=password)
                user_id = user["user_id"]

            cursor = test_db_connection.cursor()
            cursor.execute("UPDATE users SET is_verified = TRUE WHERE id = %s", (user_id,))
            test_db_connection.commit()
            cursor.close()

        with TestClient(app) as client:
            response = client.post(
                "/api/auth/login", json={"identifier": email, "password": password}
            )
            assert response.status_code == 200, f"Login failed: {response.json()}"
            yield client
    except Exception as e:
        test_db_connection.rollback()
        raise


@pytest.fixture
def second_authenticated_client(test_environment_setup, second_test_user):
    """Cliente autenticado para segundo usuario usando el environment setup compartido"""
    from fastapi.testclient import TestClient

    app = test_environment_setup["app"]

    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={
                "identifier": second_test_user["email"],
                "password": second_test_user["password"],
            },
        )
        assert response.status_code == 200, f"Login failed for second user: {response.json()}"
        yield client


@pytest.fixture
def authenticated_client_with_redis_old(test_db_connection, clean_redis, worker_id):
    """Cliente autenticado con FakeRedis inyectado para tests de sesiones - único por worker"""
    from unittest.mock import patch

    from fastapi import Response
    from fastapi.testclient import TestClient

    from app.database.database import get_db
    from app.routers.db_connections import get_redis_client
    from app.services.auth_service import AuthService
    from main import app

    # Rollback cualquier transacción fallida antes de empezar
    try:
        test_db_connection.rollback()
    except:
        pass

    # Usar worker_id para crear usuarios únicos por worker
    if worker_id == "master":
        suffix = ""
    else:
        suffix = f"_{worker_id}"

    email = f"test_e2e_old{suffix}@example.com"
    username = f"testuser_e2e_old{suffix}"
    password = "Test123!@#"

    try:
        # Intentar obtener usuario existente primero
        cursor = test_db_connection.cursor()
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()

        if existing_user:
            # Si existe, solo asegurar que está verificado
            user_id = existing_user[0]
            cursor.execute("UPDATE users SET is_verified = TRUE WHERE id = %s", (user_id,))
            test_db_connection.commit()
            cursor.close()
        else:
            cursor.close()
            # Si no existe, crear el usuario usando SQLAlchemy Session
            from app.database.session import SessionLocal

            with SessionLocal() as session:
                auth_service = AuthService(session)
                user = auth_service.create_user(username=username, email=email, password=password)
                user_id = user["user_id"]

            cursor = test_db_connection.cursor()
            cursor.execute("UPDATE users SET is_verified = TRUE WHERE id = %s", (user_id,))
            test_db_connection.commit()
            cursor.close()

        test_user = {"id": user_id, "username": username, "email": email, "password": password}
    except Exception as e:
        test_db_connection.rollback()
        raise

    # Guardar set_cookie original
    original_set_cookie = Response.set_cookie

    # Wrapper para set_cookie que fuerza secure=False en tests
    def test_set_cookie(self, *args, **kwargs):
        kwargs["secure"] = False
        return original_set_cookie(self, *args, **kwargs)

    Response.set_cookie = test_set_cookie

    # Mock get_db con wrapper que permite commits pero bloquea close
    class ConnectionWrapper:
        """Wrapper para conexión de DB que ignora close() durante tests"""

        def __init__(self, connection):
            self._connection = connection

        def __getattr__(self, name):
            # Interceptar solo close() para no cerrar la conexión de test
            # PERMITIR commit() para que el flujo de autenticación funcione
            if name == "close":
                return lambda: None  # No hacer nada
            return getattr(self._connection, name)

    def mock_get_db():
        return ConnectionWrapper(test_db_connection)

    def override_get_db():
        try:
            # Usar ConnectionWrapper para la dependencia también
            yield ConnectionWrapper(test_db_connection)
        finally:
            pass

    # Override de dependencies de FastAPI
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis_client] = lambda: clean_redis

    # Mock para get_redis_client que devuelve nuestro FakeRedis
    def mock_get_redis_client():
        return clean_redis

    # Parchear todas las referencias a get_db y Redis (para middleware y otras partes no FastAPI)
    with (
        patch("app.database.database.get_db", mock_get_db),
        patch("app.utils.security_logger.get_db", mock_get_db),
        patch("app.middleware.rate_limiting.get_db", mock_get_db),
        patch("app.middleware.csrf_protection.get_db", mock_get_db),
        patch("app.utils.redis_client.get_redis_client", mock_get_redis_client),
        patch("app.utils.redis_session_cache.get_redis_client", mock_get_redis_client),
    ):

        with TestClient(app) as client:
            # Login para autenticar
            response = client.post(
                "/api/auth/login",
                json={"identifier": test_user["email"], "password": test_user["password"]},
            )
            assert response.status_code == 200, f"Login failed: {response.json()}"

            yield client

    # Restaurar
    Response.set_cookie = original_set_cookie
    # Limpiar overrides solo al final del test
    app.dependency_overrides.clear()


@pytest.fixture
def unauthenticated_client():
    """Cliente sin autenticación (fresh TestClient)"""
    from fastapi.testclient import TestClient

    from main import app

    # Crear un cliente completamente nuevo sin cookies
    with TestClient(app) as fresh_client:
        yield fresh_client


@pytest.fixture
def e2e_encryption_setup(test_environment_setup, db_session, worker_id):
    """
    Setup completo para tests E2E de encryption - único por worker.

    Retorna un dict con:
    - client: TestClient autenticado
    - user: Dict con datos del usuario
    - project: Dict con datos del proyecto
    - db: SQLAlchemy Session
    - redis: Cliente Redis mockeado
    """
    from fastapi.testclient import TestClient

    from app.crud.project_crud import ProjectCRUD
    from app.models.orm import User
    from app.services.auth_service import AuthService

    app = test_environment_setup["app"]

    # Crear usuario único por worker
    if worker_id == "master":
        suffix = ""
    else:
        suffix = f"_{worker_id}"

    email = f"encryption_test{suffix}@example.com"
    username = f"encryption_user{suffix}"
    password = "SecurePass123!@#"

    try:
        # Intentar obtener usuario existente primero usando SQLAlchemy
        existing_user = db_session.query(User).filter(User.email == email).first()

        if existing_user:
            user_id = str(existing_user.id)
            existing_user.is_verified = True
            db_session.commit()
        else:
            # Crear nuevo usuario
            auth_service = AuthService(db_session)
            user = auth_service.create_user(username=username, email=email, password=password)
            user_id = user["user_id"]

            created_user = db_session.query(User).filter(User.id == user_id).first()
            if created_user:
                created_user.is_verified = True
                db_session.commit()

        user_data = {"id": user_id, "username": username, "email": email, "password": password}

        # Crear proyecto para este usuario usando ORM
        project = ProjectCRUD.create_project_orm(
            db=db_session,
            owner_id=user_id,
            name=f"Encryption Test Project {suffix}",
            description="Project for encryption E2E tests",
            origin_db="PostgreSQL",
            destination_db="MySQL",
            status="active",
        )

        # Crear cliente autenticado
        with TestClient(app) as client:
            response = client.post(
                "/api/auth/login", json={"identifier": email, "password": password}
            )
            assert response.status_code == 200, f"Login failed: {response.json()}"

            yield {
                "client": client,
                "user": user_data,
                "project": project,
                "db": db_session,
                "raw_db": test_environment_setup["db"],
                "redis": test_environment_setup["redis"],
            }

    except Exception as e:
        db_session.rollback()
        raise


# ============================================================================
# DATABASE CONNECTION FIXTURES
# ============================================================================


@pytest.fixture
def postgres_connection_config():
    """PostgreSQL test database configuration"""
    return {
        "dialect": "postgresql",
        "host": "localhost",
        "port": 5433,
        "database": "test_database",
        "user": "test_user",
        "password": "test_password",
        "timeout": 30,
        "ssl_mode": "disable",  # BD de test local sin TLS
    }


@pytest.fixture
def mysql_connection_config():
    """MySQL test database configuration"""
    return {
        "dialect": "mysql",
        "host": "localhost",
        "port": 3307,
        "database": "test_database",
        "user": "test_user",
        "password": "test_password",
        "timeout": 30,
        "ssl_mode": "disable",  # BD de test local sin TLS
    }


@pytest.fixture
def postgres_invalid_config():
    """Invalid PostgreSQL configuration (wrong password)"""
    return {
        "dialect": "postgresql",
        "host": "localhost",
        "port": 5433,
        "database": "test_database",
        "user": "test_user",
        "password": "wrong_password",
        "timeout": 30,
        "ssl_mode": "disable",  # BD de test local sin TLS
    }


@pytest.fixture
def mysql_invalid_config():
    """Invalid MySQL configuration (wrong password)"""
    return {
        "dialect": "mysql",
        "host": "localhost",
        "port": 3307,
        "database": "test_database",
        "user": "test_user",
        "password": "wrong_password",
        "timeout": 30,
        "ssl_mode": "disable",  # BD de test local sin TLS
    }


# ============================================================================
# ENCRYPTION KEY FIXTURE
# ============================================================================


@pytest.fixture(scope="session", autouse=True)
def set_encryption_key():
    """Asegurar que ENCRYPTION_MASTER_KEY está configurada para tests"""
    original_key = os.getenv("ENCRYPTION_MASTER_KEY")

    # Set test encryption key
    test_key = "test-encryption-key-min-32-chars-long-for-security"
    os.environ["ENCRYPTION_MASTER_KEY"] = test_key

    yield test_key

    # Restore original key
    if original_key:
        os.environ["ENCRYPTION_MASTER_KEY"] = original_key
    else:
        os.environ.pop("ENCRYPTION_MASTER_KEY", None)
