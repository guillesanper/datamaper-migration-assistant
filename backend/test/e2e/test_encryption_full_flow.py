# backend/test/e2e/test_encryption_full_flow.py
"""
Tests E2E del flujo completo de encriptación

Cobertura:
- Flujo completo: setup → verify → crear datos → leer datos → logout
- Múltiples usuarios en mismo proyecto
- Session hijacking detection
- Expiración de sesiones
- Refresh de sesiones
- Workflow real de usuario
"""

import time

import pytest
from fastapi import status

from app.crud import mappings_crud, schemas_crud
from app.services.encryption_service import EncryptionService

# ============================================================================
# TESTS DE FLUJO COMPLETO
# ============================================================================


@pytest.mark.e2e
@pytest.mark.encryption
def test_full_encryption_workflow(e2e_encryption_setup):
    """Test: Flujo completo de encriptación de principio a fin"""
    authenticated_client = e2e_encryption_setup["client"]
    test_user = e2e_encryption_setup["user"]
    test_project = e2e_encryption_setup["project"]
    clean_db = e2e_encryption_setup["db"]
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # 1. SETUP: Configurar cifrado
    setup_response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )
    assert setup_response.status_code == status.HTTP_200_OK
    assert setup_response.json()["encryption_enabled"] is True

    # 2. VERIFY: Desbloquear proyecto
    verify_response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
    )
    assert verify_response.status_code == status.HTTP_200_OK
    assert verify_response.json()["valid"] is True

    # Verificar cookie establecida
    assert f"enc_session_{project_id}" in verify_response.cookies

    # 3. CHECK SESSION: Verificar estado de sesión
    session_status = authenticated_client.get(
        f"/api/projects/{project_id}/encryption/session-status"
    )
    assert session_status.status_code == status.HTTP_200_OK
    assert session_status.json()["has_session"] is True

    # 4. CREAR DATOS: Crear tabla encriptada
    encryption_key = EncryptionService.get_encryption_key(clean_db, project_id, passphrase)

    table = schemas_crud.create_table_orm(
        clean_db, project_id, "users", "origin", test_user["id"], encryption_key
    )
    assert table["is_encrypted"] is True

    # 5. CREAR COLUMNAS: Crear columnas encriptadas
    col1 = schemas_crud.create_column_orm(
        clean_db,
        table["id"],
        "id",
        "INTEGER",
        "origin",
        False,
        True,
        True,
        test_user["id"],
        encryption_key,
    )
    col2 = schemas_crud.create_column_orm(
        clean_db,
        table["id"],
        "email",
        "VARCHAR(255)",
        "origin",
        False,
        False,
        False,
        test_user["id"],
        encryption_key,
    )

    assert col1["is_encrypted"] is True
    assert col2["is_encrypted"] is True

    # 6. CREAR MAPPING: Crear mapping encriptado
    mapping = mappings_crud.create_mapping_orm(
        clean_db,
        project_id,
        "users",
        "id",
        "customers",
        "customer_id",
        test_user["id"],
        encryption_key,
    )
    assert mapping["is_encrypted"] is True

    # 7. LEER DATOS: Verificar que se pueden leer encriptados
    tables = schemas_crud.get_tables_by_project_orm(clean_db, project_id, "origin", encryption_key)
    assert len(tables) == 1
    assert tables[0]["name"] == "users"

    columns = schemas_crud.get_columns_by_table_orm(clean_db, table["id"], encryption_key)
    assert len(columns) == 2

    mappings = mappings_crud.get_mappings_by_project_orm(clean_db, project_id, encryption_key)
    assert len(mappings) == 1

    # 8. STATS: Verificar estadísticas
    stats_response = authenticated_client.get(f"/api/projects/{project_id}/encryption/stats")
    assert stats_response.status_code == status.HTTP_200_OK
    stats = stats_response.json()
    assert stats["tables_encrypted"] == 1
    assert stats["columns_encrypted"] == 2
    assert stats["mappings_encrypted"] == 1


@pytest.mark.e2e
@pytest.mark.encryption
def test_full_flow_without_session_fails(e2e_encryption_setup):
    """Test: Intentar crear datos sin sesión falla"""
    authenticated_client = e2e_encryption_setup["client"]
    test_user = e2e_encryption_setup["user"]
    test_project = e2e_encryption_setup["project"]
    clean_db = e2e_encryption_setup["db"]
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup encryption
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    # NO hacer verify (no crear sesión)

    # Intentar crear tabla sin encryption_key debe fallar
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        schemas_crud.create_table_orm(
            clean_db, project_id, "users", "origin", test_user["id"], encryption_key=None
        )

    assert exc_info.value.status_code == 403


@pytest.mark.e2e
@pytest.mark.encryption
def test_session_refresh_workflow(e2e_encryption_setup):
    """Test: Flujo de refresh de sesión"""
    authenticated_client = e2e_encryption_setup["client"]
    test_project = e2e_encryption_setup["project"]
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup y verify
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    verify_response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
    )

    old_token = verify_response.cookies.get(f"enc_session_{project_id}")

    # Esperar un poco
    time.sleep(1)

    # Refresh sesión
    refresh_response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/refresh-session"
    )

    assert refresh_response.status_code == status.HTTP_200_OK
    assert refresh_response.json()["success"] is True

    new_token = refresh_response.cookies.get(f"enc_session_{project_id}")
    assert new_token != old_token  # Token debe cambiar

    # Verificar que sesión sigue activa
    session_status = authenticated_client.get(
        f"/api/projects/{project_id}/encryption/session-status"
    )
    assert session_status.json()["has_session"] is True


@pytest.mark.e2e
@pytest.mark.encryption
def test_disable_enable_workflow(e2e_encryption_setup):
    """Test: Flujo de deshabilitar y re-habilitar cifrado"""
    authenticated_client = e2e_encryption_setup["client"]
    test_user = e2e_encryption_setup["user"]
    test_project = e2e_encryption_setup["project"]
    clean_db = e2e_encryption_setup["db"]
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # 1. Setup
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    # 2. Verify
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
    )

    # 3. Crear datos
    encryption_key = EncryptionService.get_encryption_key(clean_db, project_id, passphrase)

    schemas_crud.create_table_orm(
        clean_db, project_id, "users", "origin", test_user["id"], encryption_key
    )

    # 4. Disable encryption
    disable_response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/disable", json={"confirm_passphrase": passphrase}
    )
    assert disable_response.status_code == status.HTTP_200_OK
    assert disable_response.json()["encryption_enabled"] is False

    # 5. Re-enable encryption
    enable_response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/enable", json={"passphrase": passphrase}
    )
    assert enable_response.status_code == status.HTTP_200_OK
    assert enable_response.json()["encryption_enabled"] is True


# ============================================================================
# TESTS DE MÚLTIPLES USUARIOS
# ============================================================================


@pytest.mark.e2e
@pytest.mark.encryption
def test_multiple_users_same_project(test_environment_setup, worker_id):
    """Test: Múltiples usuarios pueden desbloquear el mismo proyecto"""
    from test.e2e.conftest import get_unique_user_data

    from fastapi.testclient import TestClient

    from app.crud.project_crud import ProjectCRUD
    from app.database.session import SessionLocal
    from app.services.auth_service import AuthService

    app = test_environment_setup["app"]
    clean_db = test_environment_setup["db"]

    # Rollback cualquier transacción fallida
    try:
        clean_db.rollback()
    except:
        pass

    # Crear primer usuario con nombre único por worker
    username1, email1 = get_unique_user_data(worker_id, "multiuser1", "multiuser1@example.com")

    with SessionLocal() as session:
        auth_service = AuthService(session)
        user1 = auth_service.create_user(username=username1, email=email1, password="Test123!@#")

    # Marcar como verificado
    cursor = clean_db.cursor()
    cursor.execute("UPDATE users SET is_verified = TRUE WHERE id = %s", (user1["user_id"],))
    clean_db.commit()
    cursor.close()

    # Crear proyecto para usuario 1
    with SessionLocal() as session:
        test_project = ProjectCRUD.create_project_orm(
            db=session,
            owner_id=user1["user_id"],
            name=f"Multi User Test Project {worker_id}",
            description="Project for multi-user encryption tests",
            origin_db="PostgreSQL",
            destination_db="MySQL",
            status="active",
        )
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Crear segundo usuario con nombre único por worker
    username2, email2 = get_unique_user_data(worker_id, "multiuser2", "multiuser2@example.com")

    with SessionLocal() as session:
        auth_service = AuthService(session)
        user2 = auth_service.create_user(username=username2, email=email2, password="Test123!@#")

    # Marcar como verificado
    cursor = clean_db.cursor()
    cursor.execute("UPDATE users SET is_verified = TRUE WHERE id = %s", (user2["user_id"],))
    clean_db.commit()
    cursor.close()

    # Setup encryption (como usuario 1)
    with TestClient(app) as client1:
        login1 = client1.post(
            "/api/auth/login", json={"identifier": email1, "password": "Test123!@#"}
        )
        assert login1.status_code == status.HTTP_200_OK
        assert "session" in login1.cookies

        client1.post(
            f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
        )

        # Verify como usuario 1
        verify1 = client1.post(
            f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
        )
        assert verify1.status_code == status.HTTP_200_OK

    # Login como usuario 2
    with TestClient(app) as client2:
        login2 = client2.post(
            "/api/auth/login", json={"identifier": email2, "password": "Test123!@#"}
        )
        assert login2.status_code == status.HTTP_200_OK
        assert "session" in login2.cookies

        # Verify como usuario 2 (debe funcionar)
        verify2 = client2.post(
            f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
        )
        assert verify2.status_code == status.HTTP_200_OK
        assert verify2.json()["valid"] is True


# ============================================================================
# TESTS DE SESSION HIJACKING
# ============================================================================


@pytest.mark.e2e
@pytest.mark.encryption
@pytest.mark.security
def test_session_hijacking_prevention(test_environment_setup, worker_id):
    """Test: Prevención de session hijacking entre usuarios"""
    from test.e2e.conftest import get_unique_user_data

    from fastapi.testclient import TestClient

    from app.crud.project_crud import ProjectCRUD
    from app.database.session import SessionLocal
    from app.services.auth_service import AuthService

    app = test_environment_setup["app"]
    clean_db = test_environment_setup["db"]

    # Rollback cualquier transacción fallida
    try:
        clean_db.rollback()
    except:
        pass

    # Crear primer usuario con nombre único por worker
    username1, email1 = get_unique_user_data(worker_id, "hijack1", "hijack1@example.com")

    with SessionLocal() as session:
        auth_service = AuthService(session)
        user1 = auth_service.create_user(username=username1, email=email1, password="Test123!@#")

    # Marcar como verificado
    cursor = clean_db.cursor()
    cursor.execute("UPDATE users SET is_verified = TRUE WHERE id = %s", (user1["user_id"],))
    clean_db.commit()
    cursor.close()

    # Crear proyecto para usuario 1
    with SessionLocal() as session:
        test_project = ProjectCRUD.create_project_orm(
            db=session,
            owner_id=user1["user_id"],
            name=f"Hijacking Test Project {worker_id}",
            description="Project for session hijacking tests",
            origin_db="PostgreSQL",
            destination_db="MySQL",
            status="active",
        )
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Crear segundo usuario con nombre único por worker
    username2, email2 = get_unique_user_data(worker_id, "hijack2", "hijack2@example.com")

    with SessionLocal() as session:
        auth_service = AuthService(session)
        user2 = auth_service.create_user(username=username2, email=email2, password="Test123!@#")

    cursor = clean_db.cursor()
    cursor.execute("UPDATE users SET is_verified = TRUE WHERE id = %s", (user2["user_id"],))
    clean_db.commit()
    cursor.close()

    # Setup como usuario 1
    with TestClient(app) as client1:
        login1 = client1.post(
            "/api/auth/login", json={"identifier": email1, "password": "Test123!@#"}
        )
        assert login1.status_code == status.HTTP_200_OK
        assert "session" in login1.cookies

        client1.post(
            f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
        )

        # Verify como usuario 1 y obtener cookie
        verify1 = client1.post(
            f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
        )
        assert verify1.status_code == status.HTTP_200_OK

        # Obtener cookie de usuario 1
        session_cookie = verify1.cookies.get(f"enc_session_{project_id}")
        assert session_cookie is not None

    # Login como usuario 2
    with TestClient(app) as client2:
        login2 = client2.post(
            "/api/auth/login", json={"identifier": email2, "password": "Test123!@#"}
        )
        assert login2.status_code == status.HTTP_200_OK
        assert "session" in login2.cookies

        # Intentar usar la cookie de usuario 1 (session hijacking)
        client2.cookies.set(f"enc_session_{project_id}", session_cookie)

        # Verificar estado de sesión (debe detectar session hijacking)
        session_check = client2.get(f"/api/projects/{project_id}/encryption/session-status")

        # La sesión debe ser rechazada o marcada como inválida
        data = session_check.json()
        assert data["has_session"] is False or data.get("reason") == "security_violation"


# ============================================================================
# TESTS DE EDGE CASES
# ============================================================================


@pytest.mark.e2e
@pytest.mark.encryption
def test_verify_wrong_passphrase_multiple_times(e2e_encryption_setup):
    """Test: Múltiples intentos con passphrase incorrecta activa rate limiting"""
    authenticated_client = e2e_encryption_setup["client"]
    test_project = e2e_encryption_setup["project"]
    project_id = test_project["id"]
    correct_passphrase = "SecurePass123!@#"

    # Setup
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": correct_passphrase}
    )

    # 5 intentos incorrectos
    for i in range(5):
        response = authenticated_client.post(
            f"/api/projects/{project_id}/encryption/verify",
            json={"passphrase": f"WrongPassword{i}!@#"},
        )

        if i < 4:
            assert response.status_code == status.HTTP_200_OK
        else:
            # Quinto intento debe activar rate limiting
            assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.e2e
@pytest.mark.encryption
def test_create_table_read_without_session(e2e_encryption_setup):
    """Test: Crear tabla cifrada y leer sin sesión retorna datos cifrados"""
    authenticated_client = e2e_encryption_setup["client"]
    test_user = e2e_encryption_setup["user"]
    test_project = e2e_encryption_setup["project"]
    clean_db = e2e_encryption_setup["db"]
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup y verify
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
    )

    # Crear tabla con encryption_key
    encryption_key = EncryptionService.get_encryption_key(clean_db, project_id, passphrase)

    schemas_crud.create_table_orm(
        clean_db, project_id, "users", "origin", test_user["id"], encryption_key
    )

    # Leer SIN encryption_key
    tables = schemas_crud.get_tables_by_project_orm(
        clean_db, project_id, "origin", encryption_key=None
    )

    assert len(tables) == 1
    assert tables[0]["name"] is None  # Nombre cifrado
    assert tables[0]["name_encrypted"] is not None
    assert tables[0]["is_encrypted"] is True


@pytest.mark.e2e
@pytest.mark.encryption
def test_full_flow_with_unicode_data(e2e_encryption_setup):
    """Test: Flujo completo con datos Unicode"""
    authenticated_client = e2e_encryption_setup["client"]
    test_user = e2e_encryption_setup["user"]
    test_project = e2e_encryption_setup["project"]
    clean_db = e2e_encryption_setup["db"]
    project_id = test_project["id"]
    passphrase = "Contraseña123!@#Ñ"

    # Setup con passphrase Unicode
    setup_response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )
    assert setup_response.status_code == status.HTTP_200_OK

    # Verify
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
    )

    # Crear tabla con nombre Unicode
    encryption_key = EncryptionService.get_encryption_key(clean_db, project_id, passphrase)

    table = schemas_crud.create_table_orm(
        clean_db, project_id, "Usuarios_Españoles", "origin", test_user["id"], encryption_key
    )

    assert table["name"] == "Usuarios_Españoles"

    # Leer de vuelta
    tables = schemas_crud.get_tables_by_project_orm(clean_db, project_id, "origin", encryption_key)

    assert tables[0]["name"] == "Usuarios_Españoles"


@pytest.mark.e2e
@pytest.mark.encryption
def test_health_check_during_workflow(e2e_encryption_setup):
    """Test: Health check funciona durante operaciones de cifrado"""
    authenticated_client = e2e_encryption_setup["client"]
    test_project = e2e_encryption_setup["project"]
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Health check antes de setup
    health1 = authenticated_client.get("/api/projects/encryption/health")
    assert health1.status_code == status.HTTP_200_OK
    assert health1.json()["status"] == "healthy"

    # Setup
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    # Health check después de setup
    health2 = authenticated_client.get("/api/projects/encryption/health")
    assert health2.status_code == status.HTTP_200_OK
    assert health2.json()["status"] == "healthy"

    # Verify
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
    )

    # Health check con sesión activa
    health3 = authenticated_client.get("/api/projects/encryption/health")
    assert health3.status_code == status.HTTP_200_OK
    assert health3.json()["status"] == "healthy"
