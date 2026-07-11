# backend/test/unit/test_redis_session_cache.py
"""
Tests unitarios para RedisEncryptionSessionCache

Cobertura:
- Creación de sesiones con validación de parámetros
- Obtención de sesiones (con/sin project_id)
- Rotación de tokens con grace period
- Invalidación individual, por proyecto, por usuario
- Serialización/deserialización de datos
- TTL y auto-expiración
- Índices de proyecto/usuario
- Estadísticas
- Manejo de errores
"""

import secrets
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from redis import RedisError

from app.utils.redis_session_cache import RedisEncryptionSessionCache

# ============================================================================
# TESTS DE CREACIÓN DE SESIONES
# ============================================================================


@pytest.mark.unit
@pytest.mark.encryption
def test_create_session_success(mock_redis_cache):
    """Test: Crear sesión correctamente con todos los parámetros"""
    project_id = "proj-123"
    encryption_key = secrets.token_bytes(32)
    user_id = "user-456"
    timeout = 3600

    token = mock_redis_cache.create_session(project_id, encryption_key, user_id, timeout)

    # Verificar que retorna un token
    assert token is not None
    assert len(token) > 0

    # Verificar que la sesión se puede recuperar
    session = mock_redis_cache.get_session(token, project_id)
    assert session is not None
    assert session["project_id"] == project_id
    assert session["encryption_key"] == encryption_key
    assert session["user_id"] == user_id


@pytest.mark.unit
@pytest.mark.encryption
def test_create_session_default_timeout(mock_redis_cache):
    """Test: Timeout por defecto es 3 horas (10800 segundos)"""
    project_id = "proj-123"
    encryption_key = secrets.token_bytes(32)
    user_id = "user-456"

    # Sin especificar timeout (usa default)
    token = mock_redis_cache.create_session(project_id, encryption_key, user_id)

    session = mock_redis_cache.get_session(token, project_id)
    assert session is not None

    # Verificar que expires_at está ~3 horas en el futuro
    expires_at = session["expires_at"]
    now = datetime.now(timezone.utc)
    time_diff = (expires_at - now).total_seconds()
    assert 10700 < time_diff < 10900  # ~3 horas con margen


@pytest.mark.unit
@pytest.mark.encryption
def test_create_session_unique_tokens(mock_redis_cache):
    """Test: Tokens generados son únicos"""
    project_id = "proj-123"
    encryption_key = secrets.token_bytes(32)
    user_id = "user-456"

    tokens = set()
    for _ in range(10):
        token = mock_redis_cache.create_session(project_id, encryption_key, user_id)
        tokens.add(token)

    # Todos los tokens deben ser únicos
    assert len(tokens) == 10


@pytest.mark.unit
@pytest.mark.encryption
def test_create_session_indexes_created(mock_redis_cache):
    """Test: Índices de proyecto y usuario se crean correctamente"""
    project_id = "proj-123"
    encryption_key = secrets.token_bytes(32)
    user_id = "user-456"

    token = mock_redis_cache.create_session(project_id, encryption_key, user_id, 3600)

    # Verificar índice de proyecto
    project_index_key = f"enc_session:project_index:{project_id}"
    members = mock_redis_cache._redis.smembers(project_index_key)
    assert len(members) == 1
    assert token.encode() in members or token in members

    # Verificar índice de usuario
    user_index_key = f"enc_session:user_index:{user_id}"
    members = mock_redis_cache._redis.smembers(user_index_key)
    assert len(members) == 1


@pytest.mark.unit
@pytest.mark.encryption
def test_create_session_with_redis_error(fake_redis):
    """Test: Manejo de errores de Redis al crear sesión"""
    from unittest.mock import patch

    from app.utils.redis_session_cache import RedisEncryptionSessionCache

    with patch("app.utils.redis_session_cache.get_redis_client") as mock_get_redis:
        mock_redis = MagicMock()
        mock_redis.setex.side_effect = RedisError("Redis connection failed")
        mock_get_redis.return_value = mock_redis

        cache = RedisEncryptionSessionCache()

        with pytest.raises(RedisError):
            cache.create_session("proj-123", secrets.token_bytes(32), "user-456")


# ============================================================================
# TESTS DE OBTENCIÓN DE SESIONES
# ============================================================================


@pytest.mark.unit
@pytest.mark.encryption
def test_get_session_with_project_id(mock_redis_cache):
    """Test: Obtener sesión con project_id (búsqueda directa)"""
    project_id = "proj-123"
    encryption_key = secrets.token_bytes(32)
    user_id = "user-456"

    token = mock_redis_cache.create_session(project_id, encryption_key, user_id, 3600)
    session = mock_redis_cache.get_session(token, project_id)

    assert session is not None
    assert session["project_id"] == project_id
    assert session["encryption_key"] == encryption_key
    assert session["user_id"] == user_id
    assert "expires_at" in session


@pytest.mark.unit
@pytest.mark.encryption
def test_get_session_without_project_id(mock_redis_cache):
    """Test: Obtener sesión sin project_id (búsqueda por pattern)"""
    project_id = "proj-123"
    encryption_key = secrets.token_bytes(32)
    user_id = "user-456"

    token = mock_redis_cache.create_session(project_id, encryption_key, user_id, 3600)

    # Buscar sin project_id
    session = mock_redis_cache.get_session(token)

    assert session is not None
    assert session["project_id"] == project_id
    assert session["encryption_key"] == encryption_key


@pytest.mark.unit
@pytest.mark.encryption
def test_get_session_nonexistent(mock_redis_cache):
    """Test: Obtener sesión que no existe retorna None"""
    fake_token = "nonexistent-token"
    session = mock_redis_cache.get_session(fake_token, "proj-123")

    assert session is None


@pytest.mark.unit
@pytest.mark.encryption
def test_get_session_encryption_key_is_bytes(mock_redis_cache):
    """Test: encryption_key retornada es bytes, no string"""
    project_id = "proj-123"
    encryption_key = secrets.token_bytes(32)
    user_id = "user-456"

    token = mock_redis_cache.create_session(project_id, encryption_key, user_id, 3600)
    session = mock_redis_cache.get_session(token, project_id)

    assert isinstance(session["encryption_key"], bytes)
    assert len(session["encryption_key"]) == 32


# ============================================================================
# TESTS DE ROTACIÓN DE TOKENS
# ============================================================================


@pytest.mark.unit
@pytest.mark.encryption
def test_rotate_token_success(mock_redis_cache):
    """Test: Rotación de token genera nuevo token válido"""
    project_id = "proj-123"
    encryption_key = secrets.token_bytes(32)
    user_id = "user-456"

    old_token = mock_redis_cache.create_session(project_id, encryption_key, user_id, 3600)
    new_token = mock_redis_cache.rotate_token(old_token, grace_period_seconds=30)

    assert new_token is not None
    assert new_token != old_token

    # Nuevo token debe funcionar
    session = mock_redis_cache.get_session(new_token, project_id)
    assert session is not None
    assert session["encryption_key"] == encryption_key


@pytest.mark.unit
@pytest.mark.encryption
def test_rotate_token_grace_period(mock_redis_cache):
    """Test: Durante grace period, token viejo redirige al nuevo"""
    project_id = "proj-123"
    encryption_key = secrets.token_bytes(32)
    user_id = "user-456"

    old_token = mock_redis_cache.create_session(project_id, encryption_key, user_id, 3600)
    new_token = mock_redis_cache.rotate_token(old_token, grace_period_seconds=30)

    # Token viejo debe redirigir al nuevo durante grace period
    session_old = mock_redis_cache.get_session(old_token, project_id)
    session_new = mock_redis_cache.get_session(new_token, project_id)

    assert session_old is not None
    assert session_new is not None
    assert session_old["encryption_key"] == session_new["encryption_key"]


@pytest.mark.unit
@pytest.mark.encryption
def test_rotate_token_nonexistent(mock_redis_cache):
    """Test: Rotar token que no existe retorna None"""
    fake_token = "nonexistent-token"
    new_token = mock_redis_cache.rotate_token(fake_token)

    assert new_token is None


@pytest.mark.unit
@pytest.mark.encryption
def test_rotate_token_already_rotating(mock_redis_cache):
    """Test: Rotar token que ya está en rotación retorna el mismo nuevo token"""
    project_id = "proj-123"
    encryption_key = secrets.token_bytes(32)
    user_id = "user-456"

    old_token = mock_redis_cache.create_session(project_id, encryption_key, user_id, 3600)
    new_token_1 = mock_redis_cache.rotate_token(old_token, grace_period_seconds=30)
    new_token_2 = mock_redis_cache.rotate_token(old_token, grace_period_seconds=30)

    # Debe retornar el mismo token nuevo
    assert new_token_1 == new_token_2


@pytest.mark.unit
@pytest.mark.encryption
def test_rotate_token_updates_indexes(mock_redis_cache):
    """Test: Rotación actualiza índices de proyecto y usuario"""
    project_id = "proj-123"
    encryption_key = secrets.token_bytes(32)
    user_id = "user-456"

    old_token = mock_redis_cache.create_session(project_id, encryption_key, user_id, 3600)
    new_token = mock_redis_cache.rotate_token(old_token, grace_period_seconds=30)

    # Verificar que nuevo token está en índice de proyecto
    project_index_key = f"enc_session:project_index:{project_id}"
    members = mock_redis_cache._redis.smembers(project_index_key)

    # Debe contener el nuevo token
    new_token_bytes = new_token.encode() if isinstance(new_token, str) else new_token
    assert new_token_bytes in members or new_token in members


# ============================================================================
# TESTS DE INVALIDACIÓN
# ============================================================================


@pytest.mark.unit
@pytest.mark.encryption
def test_invalidate_session_success(mock_redis_cache):
    """Test: Invalidar sesión individual correctamente"""
    project_id = "proj-123"
    encryption_key = secrets.token_bytes(32)
    user_id = "user-456"

    token = mock_redis_cache.create_session(project_id, encryption_key, user_id, 3600)

    # Invalidar
    result = mock_redis_cache.invalidate_session(token, project_id)
    assert result is True

    # Verificar que ya no existe
    session = mock_redis_cache.get_session(token, project_id)
    assert session is None


@pytest.mark.unit
@pytest.mark.encryption
def test_invalidate_session_without_project_id(mock_redis_cache):
    """Test: Invalidar sesión sin project_id (búsqueda por pattern)"""
    project_id = "proj-123"
    encryption_key = secrets.token_bytes(32)
    user_id = "user-456"

    token = mock_redis_cache.create_session(project_id, encryption_key, user_id, 3600)

    # Invalidar sin project_id
    result = mock_redis_cache.invalidate_session(token)
    assert result is True

    session = mock_redis_cache.get_session(token, project_id)
    assert session is None


@pytest.mark.unit
@pytest.mark.encryption
def test_invalidate_session_nonexistent(mock_redis_cache):
    """Test: Invalidar sesión que no existe retorna False"""
    result = mock_redis_cache.invalidate_session("nonexistent-token", "proj-123")
    assert result is False


@pytest.mark.unit
@pytest.mark.encryption
def test_invalidate_project_sessions(mock_redis_cache):
    """Test: Invalidar todas las sesiones de un proyecto"""
    project_id = "proj-123"
    user_id = "user-456"
    encryption_key = secrets.token_bytes(32)

    # Crear 3 sesiones del mismo proyecto
    tokens = []
    for _ in range(3):
        token = mock_redis_cache.create_session(project_id, encryption_key, user_id, 3600)
        tokens.append(token)

    # Invalidar todas
    count = mock_redis_cache.invalidate_project_sessions(project_id)
    assert count == 3

    # Verificar que ninguna existe
    for token in tokens:
        session = mock_redis_cache.get_session(token, project_id)
        assert session is None


@pytest.mark.unit
@pytest.mark.encryption
def test_invalidate_project_sessions_empty(mock_redis_cache):
    """Test: Invalidar proyecto sin sesiones retorna 0"""
    count = mock_redis_cache.invalidate_project_sessions("nonexistent-project")
    assert count == 0


@pytest.mark.unit
@pytest.mark.encryption
def test_invalidate_user_sessions(mock_redis_cache):
    """Test: Invalidar todas las sesiones de un usuario"""
    user_id = "user-456"
    encryption_key = secrets.token_bytes(32)

    # Crear 3 sesiones del mismo usuario en diferentes proyectos
    tokens = []
    for i in range(3):
        project_id = f"proj-{i}"
        token = mock_redis_cache.create_session(project_id, encryption_key, user_id, 3600)
        tokens.append((project_id, token))

    # Invalidar todas las sesiones del usuario
    count = mock_redis_cache.invalidate_user_sessions(user_id)
    assert count == 3

    # Verificar que ninguna existe
    for project_id, token in tokens:
        session = mock_redis_cache.get_session(token, project_id)
        assert session is None


@pytest.mark.unit
@pytest.mark.encryption
def test_invalidate_user_sessions_empty(mock_redis_cache):
    """Test: Invalidar usuario sin sesiones retorna 0"""
    count = mock_redis_cache.invalidate_user_sessions("nonexistent-user")
    assert count == 0


@pytest.mark.unit
@pytest.mark.encryption
def test_invalidate_user_sessions_multiple_projects(mock_redis_cache):
    """Test: Invalidar usuario con sesiones en múltiples proyectos"""
    user_id = "user-456"
    encryption_key = secrets.token_bytes(32)

    # Crear 2 sesiones en proyecto A, 3 en proyecto B
    for i in range(2):
        mock_redis_cache.create_session("proj-A", encryption_key, user_id, 3600)

    for i in range(3):
        mock_redis_cache.create_session("proj-B", encryption_key, user_id, 3600)

    # Invalidar todas (debe eliminar 5)
    count = mock_redis_cache.invalidate_user_sessions(user_id)
    assert count == 5


# ============================================================================
# TESTS DE SERIALIZACIÓN/DESERIALIZACIÓN
# ============================================================================


@pytest.mark.unit
@pytest.mark.encryption
def test_serialize_deserialize_roundtrip(mock_redis_cache):
    """Test: Serialización y deserialización preservan datos"""
    encryption_key = secrets.token_bytes(32)
    session_data = {
        "project_id": "proj-123",
        "encryption_key": encryption_key,
        "user_id": "user-456",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "created_at": datetime.now(timezone.utc),
    }

    # Serializar
    json_str = mock_redis_cache._serialize_session(session_data)
    assert isinstance(json_str, str)

    # Deserializar
    recovered = mock_redis_cache._deserialize_session(json_str)

    assert recovered["project_id"] == session_data["project_id"]
    assert recovered["encryption_key"] == encryption_key
    assert recovered["user_id"] == session_data["user_id"]
    assert isinstance(recovered["expires_at"], datetime)
    assert isinstance(recovered["created_at"], datetime)


@pytest.mark.unit
@pytest.mark.encryption
def test_serialize_with_rotation_fields(mock_redis_cache):
    """Test: Serialización incluye campos de rotación"""
    encryption_key = secrets.token_bytes(32)
    session_data = {
        "project_id": "proj-123",
        "encryption_key": encryption_key,
        "user_id": "user-456",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "created_at": datetime.now(timezone.utc),
        "rotating": True,
        "rotated_to": "new-token-abc",
        "rotation_expires": datetime.now(timezone.utc) + timedelta(seconds=30),
    }

    json_str = mock_redis_cache._serialize_session(session_data)
    recovered = mock_redis_cache._deserialize_session(json_str)

    assert recovered["rotating"] is True
    assert recovered["rotated_to"] == "new-token-abc"
    assert isinstance(recovered["rotation_expires"], datetime)


# ============================================================================
# TESTS DE ESTADÍSTICAS
# ============================================================================


@pytest.mark.unit
@pytest.mark.encryption
def test_get_stats_empty(mock_redis_cache):
    """Test: Estadísticas con cache vacío"""
    stats = mock_redis_cache.get_stats()

    assert stats["total_sessions"] == 0
    assert stats["active_sessions"] == 0
    assert stats["expired_sessions"] == 0


@pytest.mark.unit
@pytest.mark.encryption
def test_get_stats_with_sessions(mock_redis_cache):
    """Test: Estadísticas con sesiones activas"""
    encryption_key = secrets.token_bytes(32)

    # Crear 5 sesiones
    for i in range(5):
        mock_redis_cache.create_session(f"proj-{i}", encryption_key, "user-123", 3600)

    stats = mock_redis_cache.get_stats()

    assert stats["total_sessions"] == 5
    assert stats["active_sessions"] == 5


# ============================================================================
# TESTS DE CLEANUP
# ============================================================================


@pytest.mark.unit
@pytest.mark.encryption
def test_cleanup_expired_returns_zero(mock_redis_cache):
    """Test: cleanup_expired retorna 0 (Redis TTL maneja expiración)"""
    count = mock_redis_cache.cleanup_expired()
    assert count == 0


# ============================================================================
# TESTS DE TTL Y AUTO-EXPIRACIÓN
# ============================================================================


@pytest.mark.unit
@pytest.mark.encryption
def test_session_has_ttl(mock_redis_cache):
    """Test: Sesión tiene TTL configurado en Redis"""
    project_id = "proj-123"
    encryption_key = secrets.token_bytes(32)
    user_id = "user-456"
    timeout = 60

    token = mock_redis_cache.create_session(project_id, encryption_key, user_id, timeout)

    # Verificar TTL
    session_key = f"enc_session:{project_id}:{token}"
    ttl = mock_redis_cache._redis.ttl(session_key)

    # TTL debe estar entre 50-60 segundos (con margen por latencia)
    assert 50 <= ttl <= 60


@pytest.mark.unit
@pytest.mark.encryption
def test_project_index_has_ttl(mock_redis_cache):
    """Test: Índice de proyecto tiene TTL"""
    project_id = "proj-123"
    encryption_key = secrets.token_bytes(32)
    user_id = "user-456"
    timeout = 60

    mock_redis_cache.create_session(project_id, encryption_key, user_id, timeout)

    # Verificar TTL del índice
    project_index_key = f"enc_session:project_index:{project_id}"
    ttl = mock_redis_cache._redis.ttl(project_index_key)

    # TTL debe ser timeout + 60 segundos
    assert 110 <= ttl <= 125  # 60 + 60 con margen


# ============================================================================
# TESTS DE EDGE CASES
# ============================================================================


@pytest.mark.unit
@pytest.mark.encryption
def test_multiple_sessions_same_user_project(mock_redis_cache):
    """Test: Múltiples sesiones del mismo usuario en mismo proyecto"""
    project_id = "proj-123"
    user_id = "user-456"
    encryption_key = secrets.token_bytes(32)

    # Crear 3 sesiones
    tokens = []
    for _ in range(3):
        token = mock_redis_cache.create_session(project_id, encryption_key, user_id, 3600)
        tokens.append(token)

    # Todas deben ser diferentes
    assert len(set(tokens)) == 3

    # Todas deben ser válidas
    for token in tokens:
        session = mock_redis_cache.get_session(token, project_id)
        assert session is not None


@pytest.mark.unit
@pytest.mark.encryption
def test_session_key_format(mock_redis_cache):
    """Test: Formato de Redis keys es correcto"""
    project_id = "proj-abc-123"
    token = "token-xyz-789"

    key = mock_redis_cache._make_session_key(project_id, token)
    assert key == "enc_session:proj-abc-123:token-xyz-789"


@pytest.mark.unit
@pytest.mark.encryption
def test_project_index_key_format(mock_redis_cache):
    """Test: Formato de índice de proyecto es correcto"""
    project_id = "proj-abc-123"

    key = mock_redis_cache._make_project_index_key(project_id)
    assert key == "enc_session:project_index:proj-abc-123"


@pytest.mark.unit
@pytest.mark.encryption
def test_user_index_key_format(mock_redis_cache):
    """Test: Formato de índice de usuario es correcto"""
    user_id = "user-xyz-789"

    key = mock_redis_cache._make_user_index_key(user_id)
    assert key == "enc_session:user_index:user-xyz-789"


@pytest.mark.unit
@pytest.mark.encryption
def test_encryption_key_binary_safe(mock_redis_cache):
    """Test: encryption_key binaria se preserva correctamente"""
    project_id = "proj-123"
    user_id = "user-456"

    # Clave con bytes arbitrarios (no UTF-8)
    encryption_key = bytes([0, 1, 255, 128, 64, 32]) + secrets.token_bytes(26)

    token = mock_redis_cache.create_session(project_id, encryption_key, user_id, 3600)
    session = mock_redis_cache.get_session(token, project_id)

    # Debe ser exactamente igual
    assert session["encryption_key"] == encryption_key
