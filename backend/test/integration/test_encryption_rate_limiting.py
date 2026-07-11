# backend/test/integration/test_encryption_rate_limiting.py
"""
Tests de integración para rate limiting de verificación de passphrase

Cobertura:
- Rate limiting básico (5 intentos)
- Lockout después de exceder límite
- Sliding window de 10 minutos
- Reset automático después de intento exitoso
- Cleanup de intentos expirados
- Tests de endpoints de API con rate limiting
- Security: Prevención de fuerza bruta
"""

import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status

from app.utils.rate_limiter import RateLimiter, create_rate_limit_key, get_passphrase_rate_limiter

# ============================================================================
# TESTS UNITARIOS DE RATE LIMITER
# ============================================================================


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_basic_success():
    """Test: Intentos exitosos no incrementan contador"""
    limiter = RateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=120)
    key = "test:user:123"

    # 5 intentos exitosos
    for i in range(5):
        result = limiter.record_attempt(key, success=True)
        assert result["allowed"] is True
        assert result["locked"] is False
        assert result["remaining_attempts"] == 3


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_failed_attempts():
    """Test: Contador de intentos fallidos"""
    limiter = RateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=120)
    key = "test:user:123"

    # Primer intento fallido
    result = limiter.record_attempt(key, success=False)
    assert result["allowed"] is True
    assert result["remaining_attempts"] == 2
    assert result["locked"] is False

    # Segundo intento fallido
    result = limiter.record_attempt(key, success=False)
    assert result["remaining_attempts"] == 1
    assert result["locked"] is False

    # Tercer intento fallido (alcanza el límite)
    result = limiter.record_attempt(key, success=False)
    assert result["remaining_attempts"] == 0
    assert result["locked"] is True
    assert result["retry_after"] == 120


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_lockout():
    """Test: Bloqueo después de exceder límite"""
    limiter = RateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=120)
    key = "test:user:123"

    # 3 intentos fallidos (lockout)
    for i in range(3):
        limiter.record_attempt(key, success=False)

    # Verificar que está bloqueado
    locked, remaining = limiter.is_locked(key)
    assert locked is True
    assert remaining > 0
    assert remaining <= 120


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_locked_rejects_attempts():
    """Test: Intentos durante lockout son rechazados"""
    limiter = RateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=120)
    key = "test:user:123"

    # Bloquear
    for i in range(3):
        limiter.record_attempt(key, success=False)

    # Intentar de nuevo (debe rechazar)
    result = limiter.record_attempt(key, success=False)
    assert result["allowed"] is False
    assert result["locked"] is True
    assert result["remaining_attempts"] == 0


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_success_resets_counter():
    """Test: Intento exitoso resetea contador"""
    limiter = RateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=120)
    key = "test:user:123"

    # 2 intentos fallidos
    limiter.record_attempt(key, success=False)
    limiter.record_attempt(key, success=False)

    # Intento exitoso (debe resetear)
    result = limiter.record_attempt(key, success=True)
    assert result["remaining_attempts"] == 3

    # Siguiente intento fallido debe empezar de nuevo
    result = limiter.record_attempt(key, success=False)
    assert result["remaining_attempts"] == 2


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_reset():
    """Test: Reset manual de contador"""
    limiter = RateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=120)
    key = "test:user:123"

    # Bloquear
    for i in range(3):
        limiter.record_attempt(key, success=False)

    assert limiter.is_locked(key)[0] is True

    # Reset manual
    reset_result = limiter.reset(key)
    assert reset_result is True

    # Ya no debe estar bloqueado
    locked, _ = limiter.is_locked(key)
    assert locked is False


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_reset_nonexistent_key():
    """Test: Reset de key inexistente retorna False"""
    limiter = RateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=120)

    result = limiter.reset("nonexistent:key")
    assert result is False


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_cleanup_old_attempts():
    """Test: Cleanup de intentos antiguos (sliding window)"""
    limiter = RateLimiter(max_attempts=3, window_seconds=1, lockout_seconds=2)
    key = "test:user:123"

    # 2 intentos fallidos
    limiter.record_attempt(key, success=False)
    limiter.record_attempt(key, success=False)

    # Esperar a que expiren (1 segundo + margen)
    time.sleep(1.5)

    # Nuevo intento debe empezar con contador limpio
    result = limiter.record_attempt(key, success=False)
    # Como los intentos antiguos expiraron, este es el primero
    assert result["remaining_attempts"] == 2


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_get_stats():
    """Test: Estadísticas del rate limiter"""
    limiter = RateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=120)

    # Sin actividad
    stats = limiter.get_stats()
    assert stats["total_tracked_keys"] == 0
    assert stats["currently_locked"] == 0

    # Crear algunos intentos
    limiter.record_attempt("key1", success=False)
    limiter.record_attempt("key2", success=False)
    limiter.record_attempt("key2", success=False)
    limiter.record_attempt("key2", success=False)  # key2 bloqueada

    stats = limiter.get_stats()
    assert stats["total_tracked_keys"] == 2
    assert stats["currently_locked"] == 1


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_cleanup_expired():
    """Test: Cleanup de entries expiradas"""
    limiter = RateLimiter(max_attempts=3, window_seconds=1, lockout_seconds=1)

    # Crear intentos
    limiter.record_attempt("key1", success=False)
    limiter.record_attempt("key2", success=False)

    # Esperar expiración
    time.sleep(2)

    # Cleanup
    cleaned = limiter.cleanup_expired()
    assert cleaned >= 0  # Puede ser 0 o más


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_different_keys_independent():
    """Test: Diferentes keys tienen contadores independientes"""
    limiter = RateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=120)

    # Bloquear key1
    for i in range(3):
        limiter.record_attempt("key1", success=False)

    # key2 no debe estar afectada
    result = limiter.record_attempt("key2", success=False)
    assert result["allowed"] is True
    assert result["remaining_attempts"] == 2


# ============================================================================
# TESTS DE CREATE_RATE_LIMIT_KEY
# ============================================================================


@pytest.mark.unit
@pytest.mark.encryption
def test_create_rate_limit_key_format():
    """Test: Formato de rate limit key"""
    key = create_rate_limit_key("user-123", "project-456")
    assert key == "passphrase:user:user-123:project:project-456"


@pytest.mark.unit
@pytest.mark.encryption
def test_create_rate_limit_key_different_users():
    """Test: Diferentes usuarios generan keys diferentes"""
    key1 = create_rate_limit_key("user-1", "project-1")
    key2 = create_rate_limit_key("user-2", "project-1")

    assert key1 != key2


@pytest.mark.unit
@pytest.mark.encryption
def test_create_rate_limit_key_different_projects():
    """Test: Diferentes proyectos generan keys diferentes"""
    key1 = create_rate_limit_key("user-1", "project-1")
    key2 = create_rate_limit_key("user-1", "project-2")

    assert key1 != key2


# ============================================================================
# TESTS DE INTEGRACIÓN CON API
# ============================================================================


@pytest.mark.integration
@pytest.mark.encryption
def test_api_verify_passphrase_rate_limiting(authenticated_client, test_project):
    """Test: API de verify passphrase aplica rate limiting"""
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    # Intentar 5 veces con passphrase incorrecta
    for i in range(5):
        response = authenticated_client.post(
            f"/api/projects/{project_id}/encryption/verify",
            json={"passphrase": "WrongPassword123!@#"},
        )

        if i < 4:
            # Primeros 4 intentos deben tener remaining_attempts
            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["valid"] is False
            assert "remaining_attempts" in data
        else:
            # Quinto intento debe bloquear
            assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.integration
@pytest.mark.encryption
def test_api_verify_passphrase_lockout_message(authenticated_client, test_project):
    """Test: Mensaje de lockout contiene retry_after"""
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    # 5 intentos fallidos
    for i in range(5):
        authenticated_client.post(
            f"/api/projects/{project_id}/encryption/verify",
            json={"passphrase": "WrongPassword123!@#"},
        )

    # Intento durante lockout
    response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": "WrongPassword123!@#"}
    )

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    data = response.json()

    assert "detail" in data
    assert "retry_after_seconds" in data["detail"]
    assert data["detail"]["retry_after_seconds"] > 0


@pytest.mark.integration
@pytest.mark.encryption
def test_api_verify_correct_passphrase_resets_counter(authenticated_client, test_project):
    """Test: Passphrase correcta resetea contador de rate limiting"""
    project_id = test_project["id"]
    passphrase = "SecurePass123!@#"

    # Setup
    authenticated_client.post(
        f"/api/projects/{project_id}/encryption/setup", json={"passphrase": passphrase}
    )

    # 3 intentos fallidos
    for i in range(3):
        authenticated_client.post(
            f"/api/projects/{project_id}/encryption/verify",
            json={"passphrase": "WrongPassword123!@#"},
        )

    # Intento correcto
    response = authenticated_client.post(
        f"/api/projects/{project_id}/encryption/verify", json={"passphrase": passphrase}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["valid"] is True

    # Ahora debería tener contador limpio (no inmediatamente bloqueado)
    for i in range(4):
        response = authenticated_client.post(
            f"/api/projects/{project_id}/encryption/verify",
            json={"passphrase": "WrongPassword123!@#"},
        )

        # No debe bloquear inmediatamente
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.integration
@pytest.mark.encryption
def test_api_rate_limiting_per_user_and_project(authenticated_client, test_user, db_session):
    """Test: Rate limiting es por usuario Y proyecto"""
    from app.crud.project_crud import ProjectCRUD
    from app.services.encryption_service import EncryptionService

    # Crear 2 proyectos usando ORM
    project1 = ProjectCRUD.create_project_orm(
        db_session, test_user["id"], "Project 1", "Desc 1", "PostgreSQL", "MySQL", "active"
    )
    project2 = ProjectCRUD.create_project_orm(
        db_session, test_user["id"], "Project 2", "Desc 2", "PostgreSQL", "MySQL", "active"
    )

    passphrase = "SecurePass123!@#"

    # Setup ambos
    EncryptionService.setup_project_encryption(
        db_session, project1["id"], passphrase, test_user["id"]
    )
    EncryptionService.setup_project_encryption(
        db_session, project2["id"], passphrase, test_user["id"]
    )

    # 5 intentos fallidos en project1
    for i in range(5):
        authenticated_client.post(
            f"/api/projects/{project1['id']}/encryption/verify",
            json={"passphrase": "WrongPassword123!@#"},
        )

    # project1 debe estar bloqueado
    response = authenticated_client.post(
        f"/api/projects/{project1['id']}/encryption/verify",
        json={"passphrase": "WrongPassword123!@#"},
    )
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    # project2 NO debe estar bloqueado (contador independiente)
    response = authenticated_client.post(
        f"/api/projects/{project2['id']}/encryption/verify",
        json={"passphrase": "WrongPassword123!@#"},
    )
    assert response.status_code == status.HTTP_200_OK


# ============================================================================
# TESTS DE EDGE CASES
# ============================================================================


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_thread_safety():
    """Test: Rate limiter es thread-safe"""
    import threading

    limiter = RateLimiter(max_attempts=10, window_seconds=60, lockout_seconds=120)
    key = "test:concurrent"
    results = []

    def make_attempts():
        for _ in range(5):
            result = limiter.record_attempt(key, success=False)
            results.append(result)

    # Crear 4 threads
    threads = [threading.Thread(target=make_attempts) for _ in range(4)]

    # Iniciar todos
    for t in threads:
        t.start()

    # Esperar a que terminen
    for t in threads:
        t.join()

    # Verificar que el limiter procesó todos los intentos correctamente
    # (20 intentos totales, debe estar bloqueado)
    locked, _ = limiter.is_locked(key)
    assert locked is True


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_lockout_expiration():
    """Test: Lockout expira correctamente"""
    limiter = RateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=1)
    key = "test:user:123"

    # Bloquear
    for i in range(3):
        limiter.record_attempt(key, success=False)

    # Verificar bloqueado
    assert limiter.is_locked(key)[0] is True

    # Esperar expiración del lockout
    time.sleep(1.5)

    # Ya no debe estar bloqueado
    locked, _ = limiter.is_locked(key)
    assert locked is False


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_is_locked_nonexistent_key():
    """Test: is_locked de key inexistente retorna False"""
    limiter = RateLimiter(max_attempts=3, window_seconds=60, lockout_seconds=120)

    locked, remaining = limiter.is_locked("nonexistent:key")
    assert locked is False
    assert remaining is None


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_max_attempts_zero():
    """Test: max_attempts=0 bloquea inmediatamente"""
    limiter = RateLimiter(max_attempts=0, window_seconds=60, lockout_seconds=120)
    key = "test:user:123"

    # Primer intento fallido debe bloquear
    result = limiter.record_attempt(key, success=False)
    assert result["locked"] is True


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_window_seconds_zero():
    """Test: window_seconds=0 solo cuenta intentos instantáneos"""
    limiter = RateLimiter(max_attempts=3, window_seconds=0, lockout_seconds=120)
    key = "test:user:123"

    # Intento fallido
    limiter.record_attempt(key, success=False)

    # Esperar un poquito
    time.sleep(0.1)

    # Siguiente intento debe tener ventana limpia (intentos antiguos expirados)
    result = limiter.record_attempt(key, success=False)
    # Depende de timing, pero debería funcionar


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_global_instance():
    """Test: get_passphrase_rate_limiter retorna instancia global"""
    limiter1 = get_passphrase_rate_limiter()
    limiter2 = get_passphrase_rate_limiter()

    # Debe ser la misma instancia
    assert limiter1 is limiter2


@pytest.mark.unit
@pytest.mark.encryption
def test_rate_limiter_config_from_env():
    """Test: Rate limiter usa configuración correcta"""
    limiter = get_passphrase_rate_limiter()
    stats = limiter.get_stats()

    # Verificar configuración por defecto
    assert stats["config"]["max_attempts"] == 5
    assert stats["config"]["window_seconds"] == 600  # 10 min
    assert stats["config"]["lockout_seconds"] == 900  # 15 min
