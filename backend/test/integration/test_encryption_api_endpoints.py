# backend/test/integration/test_encryption_api_endpoints.py
"""
Tests de integración E2E para endpoints de la API de encriptación

Cobertura:
- POST /encryption/setup - Configuración inicial
- POST /encryption/verify - Verificación de passphrase
- GET /encryption/session-status - Estado de sesión
- POST /encryption/refresh-session - Rotación de sesión
- GET /encryption/stats - Estadísticas de cifrado
- GET /encryption/status - Estado de cifrado
- POST /encryption/enable - Habilitar cifrado
- POST /encryption/disable - Deshabilitar cifrado
- GET /encryption/health - Health check
- Debug endpoints (cache-stats, session-check)
"""

import time
from datetime import datetime

import pytest
from fastapi import status

# ============================================================================
# TESTS DE SETUP
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_setup_encryption_success(authenticated_client, test_project):
    """Test: Configurar cifrado correctamente"""
    project_id = test_project["id"]

    response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": "SecurePass123!@#"}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["project_id"] == project_id
    assert data["encryption_enabled"] is True
    assert "created_at" in data


@pytest.mark.integration
@pytest.mark.encryption
def test_setup_encryption_weak_passphrase(authenticated_client, test_project):
    """Test: Setup con passphrase débil debe fallar"""
    project_id = test_project["id"]

    weak_passphrases = [
        "short",  # Muy corta
        "nouppercase123",  # Sin mayúsculas
        "NOLOWERCASE123",  # Sin minúsculas
        "NoNumbers",  # Sin números
    ]

    for weak_pass in weak_passphrases:
        response = authenticated_client.post(
            f"/api/projects/{project_id}/encryption/setup", json={"passphrase": weak_pass}
        )

        # Debe fallar por validación (400 o 422)
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]


@pytest.mark.integration
@pytest.mark.encryption
def test_setup_encryption_already_configured(authenticated_client, test_project):
    """Test: Setup en proyecto ya configurado debe fallar"""
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup inicial
    response1 = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )
    assert response1.status_code == status.HTTP_200_OK

    # Segundo setup debe fallar
    response2 = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": "DifferentPass123!@#"}
    )

    assert response2.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.integration
@pytest.mark.encryption
def test_setup_encryption_nonexistent_project(authenticated_client):
    """Test: Setup en proyecto inexistente debe fallar"""
    fake_project_id = "00000000-0000-0000-0000-000000000000"

    response = authenticated_client.post(
        f"/api/projects/{fake_project_id}/encryption/setup", json={"passphrase": "SecurePass123!@#"}
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# TESTS DE VERIFY PASSPHRASE
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_verify_passphrase_success(authenticated_client, test_project):
    """Test: Verificar passphrase correcta crea sesión"""
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    # Verify
    response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["valid"] is True
    assert "expires_in_seconds" in data
    assert data["expires_in_seconds"] > 0

    # Verificar cookie httpOnly
    assert f"enc_session_{project_id}" in response.cookies


@pytest.mark.integration
@pytest.mark.encryption
def test_verify_passphrase_incorrect(authenticated_client, test_project):
    """Test: Verificar passphrase incorrecta retorna false"""
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    # Verify con passphrase incorrecta
    response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": "WrongPassword123!@#"}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["valid"] is False
    assert "remaining_attempts" in data


@pytest.mark.integration
@pytest.mark.encryption
def test_verify_passphrase_no_encryption_config(authenticated_client, test_project):
    """Test: Verify en proyecto sin cifrado configurado debe devolver valid=false"""
    project_id = test_project["id"]

    response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": "SecurePass123!@#"}
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["valid"] is False


@pytest.mark.integration
@pytest.mark.encryption
def test_verify_passphrase_creates_httponly_cookie(authenticated_client, test_project):
    """Test: Verify establece cookie httpOnly correctamente"""
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    # Verify
    response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
    )

    # Verificar que cookie existe
    cookie_name = f"enc_session_{project_id}"
    assert cookie_name in response.cookies

    # Verificar propiedades de seguridad (httponly, samesite, etc.)
    # Nota: TestClient de FastAPI no expone todas las propiedades de cookies,
    # pero al menos verificamos que existe
    cookie_value = response.cookies.get(cookie_name)
    assert cookie_value is not None
    assert len(cookie_value) > 0


# ============================================================================
# TESTS DE SESSION STATUS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_session_status_with_valid_session(authenticated_client, test_project):
    """Test: Obtener estado de sesión válida"""
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup y verify
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
    )

    # Check status
    response = authenticated_client.get(f"/api/projects/{project_id}/encryption/session-status")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["has_session"] is True
    assert data["project_id"] == project_id
    assert "expires_in_seconds" in data
    assert data["expires_in_seconds"] > 0


@pytest.mark.integration
@pytest.mark.encryption
def test_session_status_without_session(authenticated_client, test_project):
    """Test: Obtener estado sin sesión activa"""
    project_id = test_project["id"]

    response = authenticated_client.get(f"/api/projects/{project_id}/encryption/session-status")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["has_session"] is False
    assert data["project_id"] == project_id


# ============================================================================
# TESTS DE REFRESH SESSION
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_refresh_session_success(authenticated_client, test_project):
    """Test: Refrescar sesión válida genera nuevo token"""
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

    # Refresh
    refresh_response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/refresh-session"
    )

    assert refresh_response.status_code == status.HTTP_200_OK
    data = refresh_response.json()

    assert data["success"] is True
    assert data["project_id"] == project_id
    assert "expires_in_seconds" in data

    # Debe tener nueva cookie
    new_token = refresh_response.cookies.get(f"enc_session_{project_id}")
    assert new_token is not None
    assert new_token != old_token  # Token debe cambiar


@pytest.mark.integration
@pytest.mark.encryption
def test_refresh_session_without_session(authenticated_client, test_project):
    """Test: Refresh sin sesión activa debe fallar"""
    project_id = test_project["id"]

    response = authenticated_client.post(f"/api/projects/{project_id}/encryption/refresh-session")

    assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# TESTS DE ENCRYPTION STATUS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_get_encryption_status_not_configured(authenticated_client, test_project):
    """Test: Status de proyecto sin cifrado configurado"""
    project_id = test_project["id"]

    response = authenticated_client.get(f"/api/projects/{project_id}/encryption/status")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["project_id"] == project_id
    assert data["encryption_enabled"] is False
    assert data["has_encryption_config"] is False
    assert data["created_at"] is None


@pytest.mark.integration
@pytest.mark.encryption
def test_get_encryption_status_configured(authenticated_client, test_project):
    """Test: Status de proyecto con cifrado configurado"""
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    # Get status
    response = authenticated_client.get(f"/api/projects/{project_id}/encryption/status")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["project_id"] == project_id
    assert data["encryption_enabled"] is True
    assert data["has_encryption_config"] is True
    assert data["created_at"] is not None


# ============================================================================
# TESTS DE ENCRYPTION STATS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_get_encryption_stats_empty_project(authenticated_client, test_project):
    """Test: Stats de proyecto vacío"""
    project_id = test_project["id"]

    response = authenticated_client.get(f"/api/projects/{project_id}/encryption/stats")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Debe retornar todos los contadores en 0
    assert data["tables_total"] == 0
    assert data["tables_encrypted"] == 0
    assert data["columns_total"] == 0
    assert data["columns_encrypted"] == 0
    assert data["mappings_total"] == 0
    assert data["mappings_encrypted"] == 0
    assert data["encryption_percentage"] == 0.0


@pytest.mark.integration
@pytest.mark.encryption
def test_get_encryption_stats_with_data(authenticated_client, test_project, db_session):
    """Test: Stats de proyecto con datos cifrados"""
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup encryption
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    # Verify (para crear sesión)
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
    )

    # Crear algunas tablas cifradas (usando CRUD ORM directamente)
    from app.crud.schemas_crud import create_table_orm
    from app.services.encryption_service import EncryptionService

    encryption_key = EncryptionService.get_encryption_key(db_session, project_id, passphrase)

    # Crear 2 tablas
    create_table_orm(
        db_session, project_id, "users", "origin", test_project["owner_id"], encryption_key
    )
    create_table_orm(
        db_session, project_id, "products", "origin", test_project["owner_id"], encryption_key
    )

    # Get stats
    response = authenticated_client.get(f"/api/projects/{project_id}/encryption/stats")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["tables_total"] == 2
    assert data["tables_encrypted"] == 2  # Ambas cifradas


# ============================================================================
# TESTS DE ENABLE/DISABLE
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_disable_encryption(authenticated_client, test_project):
    """Test: Deshabilitar cifrado"""
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    # Disable
    response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/disable", json={"confirm_passphrase": passphrase}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["encryption_enabled"] is False


@pytest.mark.integration
@pytest.mark.encryption
def test_enable_encryption(authenticated_client, test_project):
    """Test: Re-habilitar cifrado"""
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    # Disable
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/disable", json={"confirm_passphrase": passphrase}
    )

    # Enable
    response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/enable", json={"passphrase": passphrase}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["encryption_enabled"] is True


@pytest.mark.integration
@pytest.mark.encryption
def test_enable_encryption_wrong_passphrase(authenticated_client, test_project):
    """Test: Enable con passphrase incorrecta debe fallar"""
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    # Disable
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/disable", json={"confirm_passphrase": passphrase}
    )

    # Try to enable con passphrase incorrecta
    response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/enable", json={"passphrase": "WrongPassword123!@#"}
    )

    assert response.status_code in [
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    ]


# ============================================================================
# TESTS DE ROTATE MASTER KEY (Deshabilitado)
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_rotate_master_key_disabled(authenticated_client, test_project):
    """Test: Rotación de master key está deshabilitada"""
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    # Intentar rotate (debe fallar porque está deshabilitado)
    response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/rotate-key",
        json={"old_passphrase": passphrase, "new_passphrase": "NewSecurePass123!@#"},
    )

    assert response.status_code == status.HTTP_501_NOT_IMPLEMENTED
    data = response.json()

    assert "detail" in data
    assert "error" in data["detail"]


# ============================================================================
# TESTS DE HEALTH CHECK
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_encryption_health_check(client):
    """Test: Health check del sistema de cifrado"""
    response = client.get("/api/projects/encryption/health")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert "status" in data
    assert "checks" in data
    assert data["checks"]["argon2_available"] is True
    assert data["checks"]["encryption_manager"] == "ok"


# ============================================================================
# TESTS DE DEBUG ENDPOINTS
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_debug_cache_stats(authenticated_client):
    """Test: Debug endpoint de estadísticas de caché"""
    response = authenticated_client.get("/api/projects/encryption/debug/cache-stats")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert "stats" in data
    assert "user_id" in data
    assert "timestamp" in data


@pytest.mark.integration
@pytest.mark.encryption
def test_debug_session_check_no_session(authenticated_client, test_project):
    """Test: Debug session check sin sesión activa"""
    project_id = test_project["id"]

    response = authenticated_client.get(
        f"/api/projects/{project_id}/encryption/debug/session-check"
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["project_id"] == project_id
    assert data["cookie_exists"] is False
    assert data["status"] == "NO_COOKIE"


@pytest.mark.integration
@pytest.mark.encryption
def test_debug_session_check_with_session(authenticated_client, test_project):
    """Test: Debug session check con sesión activa"""
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup y verify
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
    )

    # Check session
    response = authenticated_client.get(
        f"/api/projects/{project_id}/encryption/debug/session-check"
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["project_id"] == project_id
    assert data["cookie_exists"] is True
    assert data["status"] == "VALID"
    assert data["session_found"] is True
    assert data["has_encryption_key"] is True


# ============================================================================
# TESTS DE EDGE CASES
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_verify_passphrase_replaces_old_session(authenticated_client, test_project):
    """Test: Verify reemplaza sesión anterior"""
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    # Primera verify
    response1 = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
    )
    token1 = response1.cookies.get(f"enc_session_{project_id}")

    # Segunda verify (debe reemplazar)
    response2 = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
    )
    token2 = response2.cookies.get(f"enc_session_{project_id}")

    # Tokens deben ser diferentes
    assert token1 != token2


@pytest.mark.integration
@pytest.mark.encryption
def test_multiple_projects_different_sessions(authenticated_client, test_user, db_session):
    """Test: Múltiples proyectos pueden tener sesiones simultáneas"""
    from app.crud.project_crud import ProjectCRUD

    # Crear 2 proyectos usando ORM
    project1 = ProjectCRUD.create_project_orm(
        db_session, test_user["id"], "Project 1", "Desc 1", "PostgreSQL", "MySQL", "active"
    )
    project2 = ProjectCRUD.create_project_orm(
        db_session, test_user["id"], "Project 2", "Desc 2", "PostgreSQL", "MySQL", "active"
    )

    passphrase1 = "SecurePass123!@#"
    passphrase2 = "DifferentPass456!@#"

    # Setup ambos
    authenticated_client.post(
        f"/api/projects/{project1['id']}/encryption/setup", json={"passphrase": passphrase1}
    )
    authenticated_client.post(
        f"/api/projects/{project2['id']}/encryption/setup", json={"passphrase": passphrase2}
    )

    # Verify ambos
    response1 = authenticated_client.post(
        f"/api/projects/{project1['id']}/encryption/verify", json={"passphrase": passphrase1}
    )
    response2 = authenticated_client.post(
        f"/api/projects/{project2['id']}/encryption/verify", json={"passphrase": passphrase2}
    )

    # Ambos deben tener cookies diferentes
    cookie1 = response1.cookies.get(f"enc_session_{project1['id']}")
    cookie2 = response2.cookies.get(f"enc_session_{project2['id']}")

    assert cookie1 is not None
    assert cookie2 is not None
    assert cookie1 != cookie2


@pytest.mark.integration
@pytest.mark.encryption
def test_unauthenticated_access_denied(client, test_project):
    """Test: Acceso sin autenticación debe fallar"""
    project_id = test_project["id"]

    # Sin token de autenticación
    response = client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": "SecurePass123!@#"}
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
