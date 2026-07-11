"""
Unit tests for app.crud.user_preferences_crud (ORM version)

Tests:
- get_or_create_preferences_orm
- update_preferences_orm
"""

import uuid

import pytest
from sqlalchemy.orm import Session

from app.crud.user_preferences_crud import get_or_create_preferences_orm, update_preferences_orm
from app.models.orm.user import User

# ============================================================================
# Helpers
# ============================================================================


def create_test_user(clean_db_session: Session) -> uuid.UUID:
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        username=f"prefuser_{str(user_id)[:8]}",
        email=f"{str(user_id)[:8]}@test.com",
        password_hash="hashed_test",
        is_verified=True,
        is_deleted=False,
    )
    clean_db_session.add(user)
    clean_db_session.commit()
    return user_id


# ============================================================================
# Tests: get_or_create_preferences_orm
# ============================================================================


def test_creates_preferences_on_first_call(clean_db_session: Session):
    """Crea prefs con defaults en la primera llamada y retorna todos los campos."""
    user_id = create_test_user(clean_db_session)

    result = get_or_create_preferences_orm(clean_db_session, user_id)

    assert result is not None
    assert "language" in result
    assert "timezone" in result
    assert "default_export_format" in result
    assert "default_db_type" in result
    assert "email_notifications" in result
    assert "in_app_notifications" in result
    assert "user_id" in result

    # Valores por defecto esperados
    assert result["language"] == "es"
    assert result["timezone"] == "UTC"
    assert result["default_export_format"] == "xlsx"
    assert result["default_db_type"] is None
    assert isinstance(result["email_notifications"], dict)
    assert isinstance(result["in_app_notifications"], dict)


def test_returns_existing_on_second_call(clean_db_session: Session):
    """La segunda llamada no duplica la fila."""
    from app.models.orm.user_preferences import UserPreferences

    user_id = create_test_user(clean_db_session)

    get_or_create_preferences_orm(clean_db_session, user_id)
    get_or_create_preferences_orm(clean_db_session, user_id)

    count = (
        clean_db_session.query(UserPreferences).filter(UserPreferences.user_id == user_id).count()
    )
    assert count == 1


def test_user_id_serialized_as_string(clean_db_session: Session):
    """El campo user_id del dict retornado es de tipo str."""
    user_id = create_test_user(clean_db_session)

    result = get_or_create_preferences_orm(clean_db_session, user_id)

    assert isinstance(result["user_id"], str)


# ============================================================================
# Tests: update_preferences_orm
# ============================================================================


def test_update_language(clean_db_session: Session):
    """Cambia el campo language correctamente."""
    user_id = create_test_user(clean_db_session)
    get_or_create_preferences_orm(clean_db_session, user_id)

    result = update_preferences_orm(clean_db_session, user_id, {"language": "en"})

    assert result is not None
    assert result["language"] == "en"


def test_update_multiple_fields(clean_db_session: Session):
    """Actualiza varios campos en una sola llamada."""
    user_id = create_test_user(clean_db_session)
    get_or_create_preferences_orm(clean_db_session, user_id)

    result = update_preferences_orm(
        clean_db_session,
        user_id,
        {
            "language": "en",
            "timezone": "America/New_York",
            "default_db_type": "PostgreSQL",
            "default_export_format": "csv",
        },
    )

    assert result is not None
    assert result["language"] == "en"
    assert result["timezone"] == "America/New_York"
    assert result["default_db_type"] == "PostgreSQL"
    assert result["default_export_format"] == "csv"


def test_returns_none_if_no_preferences_exist(clean_db_session: Session):
    """Si no existen prefs (sin llamar get_or_create antes), retorna None."""
    user_id = create_test_user(clean_db_session)

    result = update_preferences_orm(clean_db_session, user_id, {"language": "en"})

    assert result is None


def test_protects_user_id(clean_db_session: Session):
    """Pasar user_id en update_data no cambia al propietario."""
    user_id = create_test_user(clean_db_session)
    get_or_create_preferences_orm(clean_db_session, user_id)

    other_id = uuid.uuid4()
    result = update_preferences_orm(
        clean_db_session, user_id, {"user_id": str(other_id), "language": "en"}
    )

    assert result is not None
    assert result["user_id"] == str(user_id)


def test_merge_email_notifications(clean_db_session: Session):
    """Actualizar una clave de email_notifications no elimina las demás (merge)."""
    user_id = create_test_user(clean_db_session)
    get_or_create_preferences_orm(clean_db_session, user_id)

    # Establecer estado inicial con dos claves
    update_preferences_orm(
        clean_db_session,
        user_id,
        {"email_notifications": {"invitations": True, "comments": False}},
    )

    # Actualizar solo 'invitations'
    result = update_preferences_orm(
        clean_db_session, user_id, {"email_notifications": {"invitations": False}}
    )

    assert result is not None
    notifs = result["email_notifications"]
    assert notifs["invitations"] is False
    # 'comments' debe preservarse del merge anterior
    assert notifs["comments"] is False


def test_merge_in_app_notifications(clean_db_session: Session):
    """Mismo patrón de merge para in_app_notifications."""
    user_id = create_test_user(clean_db_session)
    get_or_create_preferences_orm(clean_db_session, user_id)

    update_preferences_orm(
        clean_db_session,
        user_id,
        {"in_app_notifications": {"mentions": True, "system": True}},
    )

    result = update_preferences_orm(
        clean_db_session, user_id, {"in_app_notifications": {"mentions": False}}
    )

    assert result is not None
    notifs = result["in_app_notifications"]
    assert notifs["mentions"] is False
    assert notifs["system"] is True


def test_update_returns_all_fields(clean_db_session: Session):
    """El dict retornado por update contiene todos los campos del modelo."""
    user_id = create_test_user(clean_db_session)
    get_or_create_preferences_orm(clean_db_session, user_id)

    result = update_preferences_orm(clean_db_session, user_id, {"language": "en"})

    assert result is not None
    for field in (
        "user_id",
        "language",
        "timezone",
        "default_db_type",
        "default_export_format",
        "email_notifications",
        "in_app_notifications",
    ):
        assert field in result, f"Campo '{field}' no encontrado en el resultado"
