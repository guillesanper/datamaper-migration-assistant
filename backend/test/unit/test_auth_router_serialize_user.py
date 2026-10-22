# test/unit/test_auth_router_serialize_user.py
"""
Tests unitarios para serialize_user de app.routers.auth
Módulo: serialización a JSON de los datos de usuario que devuelve la API de autenticación
"""

import json
from datetime import date, datetime, timezone

from app.routers.auth import serialize_user


def _user_like_get_user_by_id_orm():
    """Diccionario con la forma que devuelve user_crud.get_user_by_id_orm"""
    now = datetime(2026, 10, 10, 13, 1, 17, tzinfo=timezone.utc)
    return {
        "id": "31983d0c-e875-4803-8d38-d448e550e470",
        "username": "fase4_a",
        "email": "fase4_a@example.com",
        "avatar_url": None,
        "totp_secret": None,
        "totp_enabled": False,
        "is_verified": True,
        "is_deleted": False,
        "failed_login_attempts": 0,
        "locked_until": None,
        "last_login_at": None,
        "last_login_ip": None,
        "password_changed_at": now,
        "created_at": now,
        "updated_at": now,
    }


class TestSerializeUser:
    """Tests para la función serialize_user()"""

    def test_serialize_user_returns_none_for_none(self):
        """Test: Debe devolver None si no hay usuario"""
        assert serialize_user(None) is None

    def test_serialize_user_returns_none_for_empty_dict(self):
        """Test: Debe devolver None si el diccionario está vacío"""
        assert serialize_user({}) is None

    def test_serialize_user_converts_known_datetime_fields(self):
        """Test: Debe convertir a ISO los campos datetime de siempre"""
        moment = datetime(2026, 10, 10, 13, 1, 17, tzinfo=timezone.utc)
        user = {
            "created_at": moment,
            "updated_at": moment,
            "last_login_at": moment,
            "locked_until": moment,
        }

        result = serialize_user(user)

        assert result is not None
        for field in user:
            assert result[field] == moment.isoformat()

    def test_serialize_user_converts_password_changed_at(self):
        """Test: password_changed_at (datetime con server_default) debe quedar serializado"""
        moment = datetime(2026, 10, 10, 13, 1, 17, tzinfo=timezone.utc)

        result = serialize_user({"id": "u1", "password_changed_at": moment})

        assert result is not None
        assert result["password_changed_at"] == moment.isoformat()

    def test_serialize_user_converts_any_datetime_field(self):
        """Test: Cualquier campo datetime se convierte, no solo los de una lista fija"""
        moment = datetime(2026, 1, 2, 3, 4, 5)

        result = serialize_user({"id": "u1", "campo_futuro_at": moment})

        assert result is not None
        assert result["campo_futuro_at"] == "2026-01-02T03:04:05"

    def test_serialize_user_converts_date_objects(self):
        """Test: Los objetos date también deben convertirse a texto"""
        result = serialize_user({"id": "u1", "birth_date": date(2000, 2, 29)})

        assert result is not None
        assert result["birth_date"] == "2000-02-29"

    def test_serialize_user_result_is_json_serializable(self):
        """Test: Con la forma real de get_user_by_id_orm, json.dumps no debe fallar"""
        result = serialize_user(_user_like_get_user_by_id_orm())

        assert result is not None
        json.dumps(result)

    def test_serialize_user_keeps_non_datetime_values(self):
        """Test: Los valores que no son fechas se conservan tal cual"""
        user = _user_like_get_user_by_id_orm()

        result = serialize_user(user)

        assert result is not None
        assert result["id"] == user["id"]
        assert result["username"] == "fase4_a"
        assert result["is_verified"] is True
        assert result["failed_login_attempts"] == 0
        assert result["locked_until"] is None
        assert result["totp_secret"] is None

    def test_serialize_user_does_not_modify_input(self):
        """Test: No debe mutar el diccionario recibido"""
        user = _user_like_get_user_by_id_orm()
        original_created_at = user["created_at"]

        serialize_user(user)

        assert user["created_at"] is original_created_at
        assert isinstance(user["password_changed_at"], datetime)
