"""
Unit tests for ORM helper utilities

Tests para las funciones de conversión de modelos ORM a diccionarios.
Verifica que model_to_dict y models_to_dict_list manejan correctamente
todos los tipos de datos, casos edge, y conversiones especiales.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.utils.orm_helpers import model_to_dict, models_to_dict_list


# Mock de modelo ORM simple para testing
class MockUserModel:
    """Mock de modelo User para tests"""

    def __init__(self, id, username, email, is_verified, created_at, password_hash):
        self.id = id
        self.username = username
        self.email = email
        self.is_verified = is_verified
        self.created_at = created_at
        self.password_hash = password_hash

    class __mapper__:
        class Column:
            def __init__(self, name):
                self.name = name

        columns = [
            Column("id"),
            Column("username"),
            Column("email"),
            Column("is_verified"),
            Column("created_at"),
            Column("password_hash"),
        ]


class MockProjectModel:
    """Mock de modelo Project con campos JSONB"""

    def __init__(self, id, name, metadata_field, tags):
        self.id = id
        self.name = name
        self.metadata_field = metadata_field
        self.tags = tags

    class __mapper__:
        class Column:
            def __init__(self, name):
                self.name = name

        columns = [Column("id"), Column("name"), Column("metadata_field"), Column("tags")]


def test_model_to_dict_basic():
    """Test conversión básica de modelo a diccionario"""
    user_id = uuid4()
    created_at = datetime.now(timezone.utc)

    user = MockUserModel(
        id=user_id,
        username="testuser",
        email="test@example.com",
        is_verified=True,
        created_at=created_at,
        password_hash="hashed_password_123",
    )

    result = model_to_dict(user)

    assert result is not None
    assert isinstance(result, dict)
    assert result["id"] == str(user_id)  # UUID convertido a string
    assert result["username"] == "testuser"
    assert result["email"] == "test@example.com"
    assert result["is_verified"] is True
    assert result["created_at"] == created_at  # datetime sin convertir
    assert result["password_hash"] == "hashed_password_123"


def test_model_to_dict_with_none():
    """Test que None retorna None"""
    result = model_to_dict(None)
    assert result is None


def test_model_to_dict_with_exclude():
    """Test exclusión de campos sensibles"""
    user_id = uuid4()

    user = MockUserModel(
        id=user_id,
        username="testuser",
        email="test@example.com",
        is_verified=True,
        created_at=datetime.now(timezone.utc),
        password_hash="hashed_password_123",
    )

    result = model_to_dict(user, exclude=["password_hash"])

    assert result is not None
    assert "password_hash" not in result
    assert result["username"] == "testuser"
    assert result["email"] == "test@example.com"


def test_model_to_dict_with_multiple_exclude():
    """Test exclusión de múltiples campos"""
    user_id = uuid4()

    user = MockUserModel(
        id=user_id,
        username="testuser",
        email="test@example.com",
        is_verified=True,
        created_at=datetime.now(timezone.utc),
        password_hash="hashed_password_123",
    )

    result = model_to_dict(user, exclude=["password_hash", "email"])

    assert result is not None
    assert "password_hash" not in result
    assert "email" not in result
    assert result["username"] == "testuser"
    assert result["is_verified"] is True


def test_model_to_dict_uuid_conversion():
    """Test que UUIDs se convierten a strings"""
    user_id = uuid4()

    user = MockUserModel(
        id=user_id,
        username="testuser",
        email="test@example.com",
        is_verified=True,
        created_at=datetime.now(timezone.utc),
        password_hash="hashed_password_123",
    )

    result = model_to_dict(user)

    # El UUID debe convertirse a string
    assert isinstance(result["id"], str)
    assert result["id"] == str(user_id)
    # Verificar que es un UUID válido
    assert UUID(result["id"]) == user_id


def test_model_to_dict_datetime_preservation():
    """Test que datetime se preserva (no se convierte a string)"""
    created_at = datetime.now(timezone.utc)

    user = MockUserModel(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        is_verified=True,
        created_at=created_at,
        password_hash="hashed_password_123",
    )

    result = model_to_dict(user)

    # datetime debe preservarse como datetime object
    # FastAPI lo serializará a JSON automáticamente
    assert isinstance(result["created_at"], datetime)
    assert result["created_at"] == created_at


def test_model_to_dict_jsonb_fields():
    """Test que campos JSONB (dict, list) se preservan"""
    project_id = uuid4()
    metadata = {"key1": "value1", "key2": 123, "nested": {"inner": "data"}}
    tags = ["tag1", "tag2", "tag3"]

    project = MockProjectModel(
        id=project_id, name="Test Project", metadata_field=metadata, tags=tags
    )

    result = model_to_dict(project)

    # JSONB fields (dict/list) deben preservarse tal cual
    assert isinstance(result["metadata_field"], dict)
    assert result["metadata_field"] == metadata
    assert isinstance(result["tags"], list)
    assert result["tags"] == tags


def test_models_to_dict_list_basic():
    """Test conversión de lista de modelos a lista de dicts"""
    users = [
        MockUserModel(
            id=uuid4(),
            username=f"user{i}",
            email=f"user{i}@example.com",
            is_verified=True,
            created_at=datetime.now(timezone.utc),
            password_hash=f"hash_{i}",
        )
        for i in range(3)
    ]

    result = models_to_dict_list(users)

    assert isinstance(result, list)
    assert len(result) == 3
    assert all(isinstance(item, dict) for item in result)
    assert result[0]["username"] == "user0"
    assert result[1]["username"] == "user1"
    assert result[2]["username"] == "user2"


def test_models_to_dict_list_empty():
    """Test que lista vacía retorna lista vacía"""
    result = models_to_dict_list([])
    assert result == []


def test_models_to_dict_list_with_exclude():
    """Test exclusión de campos en lista de modelos"""
    users = [
        MockUserModel(
            id=uuid4(),
            username=f"user{i}",
            email=f"user{i}@example.com",
            is_verified=True,
            created_at=datetime.now(timezone.utc),
            password_hash=f"hash_{i}",
        )
        for i in range(2)
    ]

    result = models_to_dict_list(users, exclude=["password_hash"])

    assert len(result) == 2
    assert all("password_hash" not in item for item in result)
    assert all("username" in item for item in result)


def test_models_to_dict_list_filters_none():
    """Test que Nones en la lista se filtran"""
    users = [
        MockUserModel(
            id=uuid4(),
            username="user1",
            email="user1@example.com",
            is_verified=True,
            created_at=datetime.now(timezone.utc),
            password_hash="hash_1",
        ),
        None,  # None debe filtrarse
        MockUserModel(
            id=uuid4(),
            username="user2",
            email="user2@example.com",
            is_verified=True,
            created_at=datetime.now(timezone.utc),
            password_hash="hash_2",
        ),
    ]

    result = models_to_dict_list(users)

    # None debe filtrarse, así que solo 2 resultados
    assert len(result) == 2
    assert result[0]["username"] == "user1"
    assert result[1]["username"] == "user2"


def test_model_to_dict_boolean_fields():
    """Test que campos boolean se preservan correctamente"""
    user = MockUserModel(
        id=uuid4(),
        username="testuser",
        email="test@example.com",
        is_verified=False,  # False específicamente
        created_at=datetime.now(timezone.utc),
        password_hash="hash",
    )

    result = model_to_dict(user)

    assert result["is_verified"] is False
    assert isinstance(result["is_verified"], bool)


def test_model_to_dict_none_values():
    """Test que campos con None se preservan"""
    # Simular modelo con campos NULL
    user = MockUserModel(
        id=uuid4(),
        username="testuser",
        email=None,  # Email puede ser NULL
        is_verified=True,
        created_at=datetime.now(timezone.utc),
        password_hash="hash",
    )

    result = model_to_dict(user)

    assert "email" in result
    assert result["email"] is None
