"""
Unit tests for app.crud.api_key_crud (ORM version)

Tests:
- create_api_key_orm
- get_user_api_keys_orm
- revoke_api_key_orm
- verify_api_key_orm
"""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.crud.api_key_crud import (
    create_api_key_orm,
    get_user_api_keys_orm,
    revoke_api_key_orm,
    verify_api_key_orm,
)
from app.models.orm.api_key import UserApiKey
from app.models.orm.user import User

# ============================================================================
# Helpers
# ============================================================================


def create_test_user(clean_db_session: Session) -> uuid.UUID:
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        username=f"apiuser_{str(user_id)[:8]}",
        email=f"{str(user_id)[:8]}@test.com",
        password_hash="hashed_test",
        is_verified=True,
        is_deleted=False,
    )
    clean_db_session.add(user)
    clean_db_session.commit()
    return user_id


# ============================================================================
# Tests: create_api_key_orm
# ============================================================================


def test_create_returns_dict_and_raw_key(clean_db_session: Session):
    """Retorna tupla (dict, str) y raw_key empieza con 'rlk_'."""
    user_id = create_test_user(clean_db_session)

    result, raw_key = create_api_key_orm(clean_db_session, user_id, "My Key", None)

    assert isinstance(result, dict)
    assert isinstance(raw_key, str)
    assert raw_key.startswith("rlk_")


def test_raw_key_format(clean_db_session: Session):
    """raw_key tiene 68 caracteres: 'rlk_' (4) + 64 hex chars."""
    user_id = create_test_user(clean_db_session)

    _, raw_key = create_api_key_orm(clean_db_session, user_id, "My Key", None)

    assert len(raw_key) == 68


def test_key_prefix_matches_raw_key(clean_db_session: Session):
    """dict['key_prefix'] == raw_key[4:12]."""
    user_id = create_test_user(clean_db_session)

    key_dict, raw_key = create_api_key_orm(clean_db_session, user_id, "My Key", None)

    assert key_dict["key_prefix"] == raw_key[4:12]


def test_key_hash_is_sha256(clean_db_session: Session):
    """El hash guardado en DB es SHA-256 de la raw_key."""
    user_id = create_test_user(clean_db_session)

    key_dict, raw_key = create_api_key_orm(clean_db_session, user_id, "My Key", None)

    expected_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    # Verificar directamente en la DB
    key_in_db = clean_db_session.query(UserApiKey).filter(UserApiKey.id == key_dict["id"]).first()
    assert key_in_db is not None
    assert key_in_db.key_hash == expected_hash

    # key_hash NO debe estar en get_user_api_keys_orm
    list_result = get_user_api_keys_orm(clean_db_session, user_id)
    assert all("key_hash" not in item for item in list_result)


def test_create_with_expiration(clean_db_session: Session):
    """expires_at se guarda correctamente."""
    user_id = create_test_user(clean_db_session)
    expires = datetime.now(timezone.utc) + timedelta(days=30)

    key_dict, _ = create_api_key_orm(clean_db_session, user_id, "Expiring Key", expires)

    assert key_dict["expires_at"] is not None


def test_create_without_expiration(clean_db_session: Session):
    """expires_at es None cuando no se pasa."""
    user_id = create_test_user(clean_db_session)

    key_dict, _ = create_api_key_orm(clean_db_session, user_id, "No Expiry", None)

    assert key_dict["expires_at"] is None


def test_is_active_true_by_default(clean_db_session: Session):
    """is_active == True por defecto."""
    user_id = create_test_user(clean_db_session)

    key_dict, _ = create_api_key_orm(clean_db_session, user_id, "My Key", None)

    assert key_dict["is_active"] is True


def test_duplicate_names_allowed(clean_db_session: Session):
    """Mismo nombre para el mismo usuario no lanza error (unique solo en key_hash)."""
    user_id = create_test_user(clean_db_session)

    key1, _ = create_api_key_orm(clean_db_session, user_id, "Same Name", None)
    key2, _ = create_api_key_orm(clean_db_session, user_id, "Same Name", None)

    assert key1["id"] != key2["id"]


# ============================================================================
# Tests: get_user_api_keys_orm
# ============================================================================


def test_returns_empty_list_when_no_keys(clean_db_session: Session):
    """Retorna lista vacía si el usuario no tiene keys."""
    user_id = create_test_user(clean_db_session)

    result = get_user_api_keys_orm(clean_db_session, user_id)

    assert result == []


def test_returns_keys_for_user(clean_db_session: Session):
    """Retorna todas las keys del usuario."""
    user_id = create_test_user(clean_db_session)

    for i in range(3):
        create_api_key_orm(clean_db_session, user_id, f"Key {i}", None)

    result = get_user_api_keys_orm(clean_db_session, user_id)

    assert len(result) == 3


def test_key_hash_not_in_result(clean_db_session: Session):
    """key_hash no aparece en ningún dict de la lista."""
    user_id = create_test_user(clean_db_session)
    create_api_key_orm(clean_db_session, user_id, "My Key", None)

    result = get_user_api_keys_orm(clean_db_session, user_id)

    assert all("key_hash" not in item for item in result)


def test_isolation_between_users(clean_db_session: Session):
    """Cada usuario solo ve sus propias keys."""
    user1_id = create_test_user(clean_db_session)
    user2_id = create_test_user(clean_db_session)

    create_api_key_orm(clean_db_session, user1_id, "Key 1", None)
    create_api_key_orm(clean_db_session, user1_id, "Key 2", None)
    create_api_key_orm(clean_db_session, user2_id, "Key A", None)

    user1_keys = get_user_api_keys_orm(clean_db_session, user1_id)
    user2_keys = get_user_api_keys_orm(clean_db_session, user2_id)

    assert len(user1_keys) == 2
    assert len(user2_keys) == 1


def test_ordered_by_created_at_desc(clean_db_session: Session):
    """Las keys más recientes aparecen primero."""
    user_id = create_test_user(clean_db_session)

    for i in range(3):
        create_api_key_orm(clean_db_session, user_id, f"Key {i}", None)

    result = get_user_api_keys_orm(clean_db_session, user_id)

    assert len(result) == 3
    # Verificar que created_at sea no-creciente en la lista
    created_ats = [r["created_at"] for r in result if r["created_at"] is not None]
    for i in range(len(created_ats) - 1):
        assert created_ats[i] >= created_ats[i + 1]


# ============================================================================
# Tests: revoke_api_key_orm
# ============================================================================


def test_revoke_sets_is_active_false(clean_db_session: Session):
    """Revocar pone is_active=False en la DB."""
    user_id = create_test_user(clean_db_session)
    key_dict, _ = create_api_key_orm(clean_db_session, user_id, "My Key", None)
    key_id = uuid.UUID(str(key_dict["id"]))

    revoke_api_key_orm(clean_db_session, user_id, key_id)

    key_in_db = clean_db_session.query(UserApiKey).filter(UserApiKey.id == key_id).first()
    assert key_in_db is not None
    assert key_in_db.is_active is False


def test_revoke_returns_true_on_success(clean_db_session: Session):
    user_id = create_test_user(clean_db_session)
    key_dict, _ = create_api_key_orm(clean_db_session, user_id, "My Key", None)
    key_id = uuid.UUID(str(key_dict["id"]))

    result = revoke_api_key_orm(clean_db_session, user_id, key_id)

    assert result is True


def test_revoke_returns_false_nonexistent(clean_db_session: Session):
    user_id = create_test_user(clean_db_session)
    fake_key_id = uuid.uuid4()

    result = revoke_api_key_orm(clean_db_session, user_id, fake_key_id)

    assert result is False


def test_revoke_returns_false_wrong_user(clean_db_session: Session):
    """Un usuario no puede revocar la key de otro."""
    user1_id = create_test_user(clean_db_session)
    user2_id = create_test_user(clean_db_session)
    key_dict, _ = create_api_key_orm(clean_db_session, user1_id, "Key of user1", None)
    key_id = uuid.UUID(str(key_dict["id"]))

    result = revoke_api_key_orm(clean_db_session, user2_id, key_id)

    assert result is False

    # La key sigue activa
    key_in_db = clean_db_session.query(UserApiKey).filter(UserApiKey.id == key_id).first()
    assert key_in_db.is_active is True


def test_revoke_already_revoked(clean_db_session: Session):
    """Revocar una key ya revocada: el CRUD no filtra por is_active, retorna True."""
    user_id = create_test_user(clean_db_session)
    key_dict, _ = create_api_key_orm(clean_db_session, user_id, "My Key", None)
    key_id = uuid.UUID(str(key_dict["id"]))

    first = revoke_api_key_orm(clean_db_session, user_id, key_id)
    second = revoke_api_key_orm(clean_db_session, user_id, key_id)

    assert first is True
    # El CRUD filtra solo por user_id+id (no is_active), así que sigue encontrando la fila
    assert second is True


# ============================================================================
# Tests: verify_api_key_orm
# ============================================================================


def test_verify_valid_key(clean_db_session: Session):
    """Una key válida retorna el dict del usuario (sin password_hash)."""
    user_id = create_test_user(clean_db_session)
    _, raw_key = create_api_key_orm(clean_db_session, user_id, "My Key", None)

    result = verify_api_key_orm(clean_db_session, raw_key)

    assert result is not None
    assert str(result["id"]) == str(user_id)
    assert "password_hash" not in result


def test_verify_updates_last_used_at(clean_db_session: Session):
    """Verificar una key actualiza last_used_at."""
    user_id = create_test_user(clean_db_session)
    key_dict, raw_key = create_api_key_orm(clean_db_session, user_id, "My Key", None)
    key_id = key_dict["id"]

    # Antes de verificar
    key_before = clean_db_session.query(UserApiKey).filter(UserApiKey.id == key_id).first()
    assert key_before.last_used_at is None

    verify_api_key_orm(clean_db_session, raw_key)

    clean_db_session.refresh(key_before)
    assert key_before.last_used_at is not None


def test_verify_invalid_key(clean_db_session: Session):
    """Un string aleatorio retorna None."""
    result = verify_api_key_orm(clean_db_session, "rlk_invalid_random_string")

    assert result is None


def test_verify_revoked_key(clean_db_session: Session):
    """Una key revocada retorna None."""
    user_id = create_test_user(clean_db_session)
    key_dict, raw_key = create_api_key_orm(clean_db_session, user_id, "My Key", None)
    key_id = uuid.UUID(str(key_dict["id"]))

    revoke_api_key_orm(clean_db_session, user_id, key_id)

    result = verify_api_key_orm(clean_db_session, raw_key)

    assert result is None


def test_verify_expired_key(clean_db_session: Session):
    """Una key con expires_at en el pasado retorna None."""
    user_id = create_test_user(clean_db_session)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    _, raw_key = create_api_key_orm(clean_db_session, user_id, "Expired Key", past)

    result = verify_api_key_orm(clean_db_session, raw_key)

    assert result is None


def test_verify_non_expired_key(clean_db_session: Session):
    """Una key con expires_at en el futuro retorna el usuario."""
    user_id = create_test_user(clean_db_session)
    future = datetime.now(timezone.utc) + timedelta(days=30)
    _, raw_key = create_api_key_orm(clean_db_session, user_id, "Future Key", future)

    result = verify_api_key_orm(clean_db_session, raw_key)

    assert result is not None
    assert str(result["id"]) == str(user_id)
