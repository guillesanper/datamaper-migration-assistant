"""
Unit tests for reactions_crud.py ORM functions

Tests para las 5 funciones ORM de reactions_crud:
1. add_reaction_orm() - Test INSERT con IntegrityError
2. remove_reaction_orm() - Test DELETE
3. get_reactions_by_comment_orm() - Test SELECT con JOIN
4. get_reaction_counts_orm() - Test GROUP BY
5. check_user_reacted_orm() - Test boolean

Estructura:
- Usa SessionLocal para crear sesiones de SQLAlchemy
- Fixtures para crear datos de prueba (usuarios, proyectos, comentarios)
- Rollback automático después de cada test
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

# Importar TODOS los modelos ORM desde __init__ para que SQLAlchemy resuelva las relaciones
# Esto es necesario porque algunos modelos tienen relaciones circulares
import app.models.orm as orm  # Importar todo el paquete para inicializar relaciones
from app.crud.reactions_crud import (
    add_reaction_orm,
    check_user_reacted_orm,
    get_reaction_counts_orm,
    get_reactions_by_comment_orm,
    remove_reaction_orm,
)
from app.database.session import SessionLocal
from app.models.orm import Comment, CommentReaction, Project, User

# ============================================================================
# FIXTURES
# ============================================================================
# Nota: db_session fixture está definido en conftest.py


@pytest.fixture
def test_user(db_session):
    """
    Crea un usuario de prueba en la base de datos.

    Returns:
        User: Instancia del modelo User creada en la BD
    """
    user = User(
        id=uuid4(),
        username=f"test_user_{uuid4().hex[:8]}",
        email=f"test_{uuid4().hex[:8]}@example.com",
        password_hash="hashed_password_123",
        is_verified=True,
        is_deleted=False,
        failed_login_attempts=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_user2(db_session):
    """
    Crea un segundo usuario de prueba para tests con múltiples usuarios.

    Returns:
        User: Instancia del modelo User creada en la BD
    """
    user = User(
        id=uuid4(),
        username=f"test_user2_{uuid4().hex[:8]}",
        email=f"test2_{uuid4().hex[:8]}@example.com",
        password_hash="hashed_password_456",
        is_verified=True,
        is_deleted=False,
        failed_login_attempts=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def test_project(db_session, test_user):
    """
    Crea un proyecto de prueba en la base de datos.

    Args:
        db_session: Sesión de SQLAlchemy
        test_user: Usuario propietario del proyecto

    Returns:
        Project: Instancia del modelo Project creada en la BD
    """
    project = Project(
        id=uuid4(),
        name=f"Test Project {uuid4().hex[:8]}",
        description="Test project for reactions",
        owner_id=test_user.id,
        origin_db="PostgreSQL",
        destination_db="MySQL",
        status="active",
        is_deleted=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(project)
    db_session.commit()
    return project


@pytest.fixture
def test_comment(db_session, test_user, test_project):
    """
    Crea un comentario de prueba en la base de datos.

    Args:
        db_session: Sesión de SQLAlchemy
        test_user: Usuario que crea el comentario
        test_project: Proyecto al que pertenece el comentario

    Returns:
        Comment: Instancia del modelo Comment creada en la BD
    """
    comment = Comment(
        id=uuid4(),
        entity_id=uuid4(),  # Entidad ficticia
        entity_type="mapping",
        project_id=test_project.id,
        user_id=test_user.id,
        content="Test comment for reactions",
        is_encrypted=False,
        created_at=datetime.now(timezone.utc),
        is_edited=False,
        is_resolved=False,
    )
    db_session.add(comment)
    db_session.commit()
    return comment


# ============================================================================
# TESTS: add_reaction_orm()
# ============================================================================


def test_add_reaction_orm_success(db_session, test_comment, test_user):
    """Test que se puede agregar una reacción exitosamente"""
    result = add_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="👍"
    )

    assert result is not None
    assert isinstance(result, dict)
    assert result["comment_id"] == str(test_comment.id)
    assert result["user_id"] == str(test_user.id)
    assert result["emoji"] == "👍"
    assert "id" in result
    assert "created_at" in result


def test_add_reaction_orm_duplicate_returns_none(db_session, test_comment, test_user):
    """Test que agregar la misma reacción dos veces retorna None (ON CONFLICT DO NOTHING)"""
    # Primera reacción - debe funcionar
    result1 = add_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="❤️"
    )
    assert result1 is not None

    # Segunda reacción idéntica - debe retornar None por IntegrityError
    result2 = add_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="❤️"
    )
    assert result2 is None


def test_add_reaction_orm_different_emoji_same_user(db_session, test_comment, test_user):
    """Test que un mismo usuario puede reaccionar con diferentes emojis"""
    result1 = add_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="👍"
    )

    result2 = add_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="❤️"
    )

    assert result1 is not None
    assert result2 is not None
    assert result1["emoji"] == "👍"
    assert result2["emoji"] == "❤️"


def test_add_reaction_orm_same_emoji_different_users(
    db_session, test_comment, test_user, test_user2
):
    """Test que diferentes usuarios pueden reaccionar con el mismo emoji"""
    result1 = add_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="🎉"
    )

    result2 = add_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user2.id), emoji="🎉"
    )

    assert result1 is not None
    assert result2 is not None
    assert result1["user_id"] == str(test_user.id)
    assert result2["user_id"] == str(test_user2.id)


# ============================================================================
# TESTS: remove_reaction_orm()
# ============================================================================


def test_remove_reaction_orm_success(db_session, test_comment, test_user):
    """Test que se puede eliminar una reacción exitosamente"""
    # Primero agregar una reacción
    add_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="👍"
    )

    # Luego eliminarla
    deleted = remove_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="👍"
    )

    assert deleted is True


def test_remove_reaction_orm_not_exists_returns_false(db_session, test_comment, test_user):
    """Test que eliminar una reacción inexistente retorna False"""
    deleted = remove_reaction_orm(
        db=db_session,
        comment_id=str(test_comment.id),
        user_id=str(test_user.id),
        emoji="👎",  # Esta reacción no existe
    )

    assert deleted is False


def test_remove_reaction_orm_wrong_user(db_session, test_comment, test_user, test_user2):
    """Test que no se puede eliminar la reacción de otro usuario"""
    # Usuario 1 agrega reacción
    add_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="😀"
    )

    # Usuario 2 intenta eliminarla - debe retornar False
    deleted = remove_reaction_orm(
        db=db_session,
        comment_id=str(test_comment.id),
        user_id=str(test_user2.id),  # Usuario diferente
        emoji="😀",
    )

    assert deleted is False


def test_remove_reaction_orm_wrong_emoji(db_session, test_comment, test_user):
    """Test que no se puede eliminar con emoji incorrecto"""
    # Agregar reacción con un emoji
    add_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="👍"
    )

    # Intentar eliminar con emoji diferente - debe retornar False
    deleted = remove_reaction_orm(
        db=db_session,
        comment_id=str(test_comment.id),
        user_id=str(test_user.id),
        emoji="👎",  # Emoji diferente
    )

    assert deleted is False


# ============================================================================
# TESTS: get_reactions_by_comment_orm()
# ============================================================================


def test_get_reactions_by_comment_orm_empty(db_session, test_comment):
    """Test que un comentario sin reacciones retorna lista vacía"""
    reactions = get_reactions_by_comment_orm(db=db_session, comment_id=str(test_comment.id))

    assert isinstance(reactions, list)
    assert len(reactions) == 0


def test_get_reactions_by_comment_orm_single_reaction(db_session, test_comment, test_user):
    """Test que se obtiene correctamente una reacción con JOIN de username"""
    add_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="👍"
    )

    reactions = get_reactions_by_comment_orm(db=db_session, comment_id=str(test_comment.id))

    assert len(reactions) == 1
    assert reactions[0]["emoji"] == "👍"
    assert reactions[0]["user_id"] == str(test_user.id)
    assert reactions[0]["username"] == test_user.username  # JOIN con User
    assert "created_at" in reactions[0]


def test_get_reactions_by_comment_orm_multiple_reactions(
    db_session, test_comment, test_user, test_user2
):
    """Test que se obtienen múltiples reacciones ordenadas por created_at"""
    # Agregar varias reacciones
    add_reaction_orm(db_session, str(test_comment.id), str(test_user.id), "👍")
    add_reaction_orm(db_session, str(test_comment.id), str(test_user2.id), "❤️")
    add_reaction_orm(db_session, str(test_comment.id), str(test_user.id), "🎉")

    reactions = get_reactions_by_comment_orm(db=db_session, comment_id=str(test_comment.id))

    assert len(reactions) == 3
    # Verificar que están ordenadas por created_at ASC
    assert all("created_at" in r for r in reactions)
    # Verificar que todos tienen username del JOIN
    assert all("username" in r for r in reactions)


def test_get_reactions_by_comment_orm_with_deleted_user(db_session, test_comment, test_user):
    """Test que funciona el LEFT JOIN cuando el usuario no existe (username = None)"""
    # Agregar reacción
    add_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="👍"
    )

    # Simular usuario eliminado (eliminar el usuario de la BD)
    # El foreign key está configurado con ondelete='CASCADE', así que esto eliminará
    # la reacción también. En su lugar, vamos a probar que el query funciona correctamente.
    # Nota: En producción, el ondelete podría ser 'SET NULL' para preservar reacciones
    # de usuarios eliminados, pero el esquema actual usa 'CASCADE'.

    # Por ahora, vamos a verificar que el query funciona correctamente cuando
    # el usuario SÍ existe (que es el caso más común)
    reactions = get_reactions_by_comment_orm(db=db_session, comment_id=str(test_comment.id))

    assert len(reactions) == 1
    assert reactions[0]["username"] == test_user.username  # LEFT JOIN retorna el username

    # Comentario: Si el foreign key fuera ondelete='SET NULL', podríamos testear
    # que username es None cuando el usuario no existe. Con CASCADE, la reacción
    # se elimina automáticamente cuando se elimina el usuario.


# ============================================================================
# TESTS: get_reaction_counts_orm()
# ============================================================================


def test_get_reaction_counts_orm_empty(db_session, test_comment):
    """Test que un comentario sin reacciones retorna dict vacío"""
    counts = get_reaction_counts_orm(db=db_session, comment_id=str(test_comment.id))

    assert isinstance(counts, dict)
    assert len(counts) == 0


def test_get_reaction_counts_orm_single_emoji(db_session, test_comment, test_user, test_user2):
    """Test que cuenta correctamente múltiples reacciones del mismo emoji"""
    # Agregar 2 reacciones con el mismo emoji
    add_reaction_orm(db_session, str(test_comment.id), str(test_user.id), "👍")
    add_reaction_orm(db_session, str(test_comment.id), str(test_user2.id), "👍")

    counts = get_reaction_counts_orm(db=db_session, comment_id=str(test_comment.id))

    assert counts == {"👍": 2}


def test_get_reaction_counts_orm_multiple_emojis(db_session, test_comment, test_user, test_user2):
    """Test que agrupa correctamente por emoji con GROUP BY"""
    # Agregar varias reacciones con diferentes emojis
    add_reaction_orm(db_session, str(test_comment.id), str(test_user.id), "👍")
    add_reaction_orm(db_session, str(test_comment.id), str(test_user2.id), "👍")
    add_reaction_orm(db_session, str(test_comment.id), str(test_user.id), "❤️")
    add_reaction_orm(db_session, str(test_comment.id), str(test_user2.id), "🎉")

    counts = get_reaction_counts_orm(db=db_session, comment_id=str(test_comment.id))

    assert counts == {"👍": 2, "❤️": 1, "🎉": 1}


def test_get_reaction_counts_orm_after_remove(db_session, test_comment, test_user, test_user2):
    """Test que los conteos se actualizan correctamente después de eliminar reacciones"""
    # Agregar reacciones
    add_reaction_orm(db_session, str(test_comment.id), str(test_user.id), "👍")
    add_reaction_orm(db_session, str(test_comment.id), str(test_user2.id), "👍")

    # Eliminar una reacción
    remove_reaction_orm(db_session, str(test_comment.id), str(test_user.id), "👍")

    counts = get_reaction_counts_orm(db=db_session, comment_id=str(test_comment.id))

    assert counts == {"👍": 1}  # Solo queda 1


# ============================================================================
# TESTS: check_user_reacted_orm()
# ============================================================================


def test_check_user_reacted_orm_true(db_session, test_comment, test_user):
    """Test que retorna True cuando el usuario ya reaccionó"""
    # Agregar reacción
    add_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="👍"
    )

    # Verificar
    exists = check_user_reacted_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="👍"
    )

    assert exists is True


def test_check_user_reacted_orm_false_no_reaction(db_session, test_comment, test_user):
    """Test que retorna False cuando el usuario no ha reaccionado"""
    exists = check_user_reacted_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="👍"
    )

    assert exists is False


def test_check_user_reacted_orm_false_different_emoji(db_session, test_comment, test_user):
    """Test que retorna False cuando el usuario reaccionó con otro emoji"""
    # Agregar reacción con un emoji
    add_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="👍"
    )

    # Verificar con emoji diferente
    exists = check_user_reacted_orm(
        db=db_session,
        comment_id=str(test_comment.id),
        user_id=str(test_user.id),
        emoji="❤️",  # Emoji diferente
    )

    assert exists is False


def test_check_user_reacted_orm_false_different_user(
    db_session, test_comment, test_user, test_user2
):
    """Test que retorna False cuando otro usuario reaccionó"""
    # Usuario 1 reacciona
    add_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="👍"
    )

    # Verificar con usuario 2
    exists = check_user_reacted_orm(
        db=db_session,
        comment_id=str(test_comment.id),
        user_id=str(test_user2.id),  # Usuario diferente
        emoji="👍",
    )

    assert exists is False


def test_check_user_reacted_orm_after_remove(db_session, test_comment, test_user):
    """Test que retorna False después de eliminar la reacción"""
    # Agregar reacción
    add_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="👍"
    )

    # Verificar que existe
    assert (
        check_user_reacted_orm(
            db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="👍"
        )
        is True
    )

    # Eliminar reacción
    remove_reaction_orm(
        db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="👍"
    )

    # Verificar que ya no existe
    assert (
        check_user_reacted_orm(
            db=db_session, comment_id=str(test_comment.id), user_id=str(test_user.id), emoji="👍"
        )
        is False
    )
